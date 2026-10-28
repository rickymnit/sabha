// The upload flow (P6.3, first version): hash the file, create the recording, PUT its parts straight to storage
// with the presigned URLs (golden rule 2: audio never passes through the API), then complete.
//
// Parts go up PARALLEL at a time; a failed part is retried PART_RETRIES times with a growing pause. The create
// call carries an Idempotency-Key, so retrying it after a dropped connection never makes a second recording.
// Not in this version (P6.3 remainder): hashing in a Web Worker for files over MAX_HASH_BYTES, and resuming after
// a page reload (upload state in IndexedDB, POST /parts for fresh URLs).

import { ApiError, apiFetch } from "../../api/client";
import type { UploadStarted } from "../../api/types";

export const PARALLEL = 3;
export const PART_RETRIES = 3;
export const MAX_HASH_BYTES = 512 * 1024 * 1024;

const TYPES_BY_EXTENSION: Record<string, string> = {
  mp3: "audio/mpeg",
  m4a: "audio/mp4",
  wav: "audio/wav",
  webm: "audio/webm",
  ogg: "audio/ogg",
  mp4: "video/mp4",
};

export interface UploadInput {
  file: File;
  type: string;
  personId: string | null;
  consentRef: string | null;
  token: string | undefined;
  /** The length the browser measured; the server keeps the expected cost worked out from it. */
  expectedDurationMs?: number | null;
  /** Bytes uploaded so far, after each part. */
  onProgress?: (sent: number, total: number) => void;
  /** For tests: fetch for the part PUTs, and a pause between retries. */
  put?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
}

export interface UploadResult {
  recording_id: string;
  status: string;
  awaiting_consent: boolean;
  duplicate_of: string | null;
}

/** Done, or held because the same file is already in the organisation: `confirm` uploads it anyway. */
export type UploadOutcome =
  | { kind: "done"; result: UploadResult }
  | { kind: "duplicate"; recording_id: string; confirm: () => Promise<UploadResult> };

export function contentTypeOf(file: File): string {
  if (file.type) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return TYPES_BY_EXTENSION[extension] ?? "application/octet-stream";
}

export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function putPart(url: string, body: Blob, put: typeof fetch, sleep: (ms: number) => Promise<void>) {
  let lastError: unknown;
  for (let attempt = 1; attempt <= PART_RETRIES; attempt += 1) {
    try {
      const response = await put(url, { method: "PUT", body });
      const etag = response.headers.get("ETag");
      if (response.ok && etag) return etag;
      lastError = new Error(`storage answered ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    if (attempt < PART_RETRIES) await sleep(1000 * 2 ** (attempt - 1));
  }
  throw new ApiError(0, "upload_failed", "Upload failed", `A part could not be uploaded: ${String(lastError)}`);
}

export async function uploadRecording(input: UploadInput): Promise<UploadOutcome> {
  const { file, token } = input;
  const put = input.put ?? fetch;
  const sleep = input.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  if (file.size > MAX_HASH_BYTES) {
    throw new ApiError(
      0,
      "file_too_large",
      "File too large",
      "Files over 512 MB are not supported by this uploader yet.",
    );
  }
  const sha256 = await sha256Hex(file);
  const started = await apiFetch<UploadStarted>("/v1/recordings", {
    method: "POST",
    token,
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: {
      type: input.type,
      person_id: input.personId,
      file_name: file.name,
      size_bytes: file.size,
      content_type: contentTypeOf(file),
      consent_ref: input.consentRef,
      ...(input.expectedDurationMs ? { expected_duration_ms: input.expectedDurationMs } : {}),
    },
  });
  const etags = new Map<number, string>();
  let sent = 0;
  const queue = [...started.parts];
  const worker = async () => {
    for (let part = queue.shift(); part; part = queue.shift()) {
      const start = (part.part_number - 1) * started.part_size;
      const body = file.slice(start, start + started.part_size);
      etags.set(part.part_number, await putPart(part.url, body, put, sleep));
      sent += body.size;
      input.onProgress?.(sent, file.size);
    }
  };
  await Promise.all(Array.from({ length: Math.min(PARALLEL, started.parts.length) }, worker));
  const parts = [...etags.entries()].sort(([a], [b]) => a - b).map(([part_number, etag]) => ({ part_number, etag }));
  const complete = (force: boolean) =>
    apiFetch<UploadResult>(`/v1/recordings/${encodeURIComponent(started.recording_id)}/complete`, {
      method: "POST",
      token,
      body: { parts, sha256, force },
    });
  try {
    return { kind: "done", result: await complete(false) };
  } catch (error) {
    if (error instanceof ApiError && error.code === "duplicate_recording") {
      return { kind: "duplicate", recording_id: started.recording_id, confirm: () => complete(true) };
    }
    throw error;
  }
}
