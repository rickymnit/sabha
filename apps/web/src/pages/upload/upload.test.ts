import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { contentTypeOf, MAX_HASH_BYTES, PART_RETRIES, sha256Hex, uploadRecording } from "./upload";

const PART_SIZE = 4;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** The API: create answers with 3 part URLs; complete answers `completeStatus` (and records its body). */
function api(completeStatus = 200) {
  const calls: { path: string; init: RequestInit }[] = [];
  const fetchMock = vi.fn(async (path: string, init: RequestInit) => {
    calls.push({ path, init });
    if (path === "/v1/recordings") {
      return json(201, {
        recording_id: "rec-1",
        upload_id: "up-1",
        part_size: PART_SIZE,
        parts: [1, 2, 3].map((n) => ({ part_number: n, url: `https://storage.example/part/${n}` })),
        expires_at: "2026-10-22T10:00:00Z",
      });
    }
    if (completeStatus === 409) {
      return json(409, { code: "duplicate_recording", title: "Duplicate recording", detail: "Already uploaded." });
    }
    return json(200, { recording_id: "rec-1", status: "UPLOADED", awaiting_consent: false, duplicate_of: null });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

/** Storage: answers each PUT with an ETag named after the part; `failures` makes that many first tries fail. */
function storage(failures: Record<number, number> = {}) {
  let inFlight = 0;
  let maxInFlight = 0;
  const bodies = new Map<number, string>();
  const put = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const n = Number(String(url).split("/").pop());
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise((resolve) => setTimeout(resolve, 1));
    inFlight -= 1;
    if ((failures[n] ?? 0) > 0) {
      failures[n] = (failures[n] ?? 0) - 1;
      return new Response("busy", { status: 503 });
    }
    bodies.set(n, await (init?.body as Blob).text());
    return new Response(null, { status: 200, headers: { ETag: `"etag-${n}"` } });
  });
  return { put: put as unknown as typeof fetch, bodies, maxInFlight: () => maxInFlight, calls: put };
}

const file = () => new File(["0123456789"], "Class 7B.mp3", { type: "audio/mpeg" });
const noWait = async () => undefined;

afterEach(() => vi.unstubAllGlobals());

describe("uploadRecording", () => {
  it("creates the recording, puts each part straight to storage and completes with the ETags and hash", async () => {
    const calls = api();
    const store = storage();
    const progress: number[] = [];
    const outcome = await uploadRecording({
      file: file(), type: "teaching", personId: "p-asha", consentRef: "form-7", token: "t",
      put: store.put, sleep: noWait, onProgress: (sent) => progress.push(sent),
    }); // prettier-ignore

    expect(outcome).toEqual({ kind: "done", result: expect.objectContaining({ recording_id: "rec-1" }) });
    const create = JSON.parse(String(calls[0]?.init.body));
    expect(create).toMatchObject({ type: "teaching", person_id: "p-asha", file_name: "Class 7B.mp3", size_bytes: 10,
                                   content_type: "audio/mpeg", consent_ref: "form-7" }); // prettier-ignore
    expect((calls[0]?.init.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
    expect([...store.bodies.entries()].sort()).toEqual([
      [1, "0123"],
      [2, "4567"],
      [3, "89"],
    ]);
    const complete = JSON.parse(String(calls[1]?.init.body));
    expect(calls[1]?.path).toBe("/v1/recordings/rec-1/complete");
    expect(complete.parts).toEqual([1, 2, 3].map((n) => ({ part_number: n, etag: `"etag-${n}"` })));
    expect(complete.sha256).toBe(await sha256Hex(file()));
    expect(complete.force).toBe(false);
    expect(progress.at(-1)).toBe(10);
    expect(store.maxInFlight()).toBeLessThanOrEqual(3);
  });

  it("retries a failed part and gives up after the last try", async () => {
    api();
    const flaky = storage({ 2: PART_RETRIES - 1 });
    await uploadRecording({ file: file(), type: "teaching", personId: null, consentRef: null, token: "t",
                            put: flaky.put, sleep: noWait }); // prettier-ignore
    expect(flaky.calls.mock.calls.filter(([url]) => String(url).endsWith("/2"))).toHaveLength(PART_RETRIES);

    api();
    const dead = storage({ 2: PART_RETRIES });
    await expect(
      uploadRecording({ file: file(), type: "teaching", personId: null, consentRef: null, token: "t",
                        put: dead.put, sleep: noWait }), // prettier-ignore
    ).rejects.toMatchObject({ code: "upload_failed" });
  });

  it("holds a duplicate until the person confirms, then completes with force", async () => {
    const calls = api(409);
    const outcome = await uploadRecording({ file: file(), type: "teaching", personId: null, consentRef: null,
                                            token: "t", put: storage().put, sleep: noWait }); // prettier-ignore
    expect(outcome.kind).toBe("duplicate");
    if (outcome.kind !== "duplicate") return;
    await expect(outcome.confirm()).rejects.toBeInstanceOf(ApiError); // the fake API keeps answering 409
    expect(JSON.parse(String(calls.at(-1)?.init.body)).force).toBe(true);
  });

  it("refuses files too large for this version before uploading anything", async () => {
    const calls = api();
    const big = new File(["x"], "big.wav");
    Object.defineProperty(big, "size", { value: MAX_HASH_BYTES + 1 });
    await expect(
      uploadRecording({ file: big, type: "teaching", personId: null, consentRef: null, token: "t" }),
    ).rejects.toMatchObject({ code: "file_too_large" });
    expect(calls).toHaveLength(0);
  });
});

describe("contentTypeOf", () => {
  it("uses the browser's type, else the extension", () => {
    expect(contentTypeOf(new File([""], "a.mp3", { type: "audio/mpeg" }))).toBe("audio/mpeg");
    expect(contentTypeOf(new File([""], "a.M4A"))).toBe("audio/mp4");
    expect(contentTypeOf(new File([""], "a.xyz"))).toBe("application/octet-stream");
  });
});
