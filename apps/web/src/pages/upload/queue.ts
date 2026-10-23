// The upload page's list of files (docs/design/03-upload.png, "Files"): what each file is doing, as a reducer so
// the page stays simple and the rules are testable. Files go up one at a time (each file's parts in parallel,
// upload.ts); a file that cannot be sent says why in plain words before anything is uploaded.

import { MAX_HASH_BYTES, type UploadOutcome } from "./upload";

export const ACCEPTED_EXTENSIONS = ["mp3", "m4a", "wav", "webm", "ogg", "mp4"] as const;
export const ACCEPT_ATTRIBUTE = ".mp3,.m4a,.wav,.webm,.ogg,.mp4,audio/*,video/mp4";

export type ItemState =
  | { kind: "ready" }
  | { kind: "invalid"; reason: string }
  | { kind: "uploading"; sent: number; total: number }
  | { kind: "done"; recordingId: string; awaitingConsent: boolean }
  | { kind: "duplicate"; confirm: Extract<UploadOutcome, { kind: "duplicate" }>["confirm"] }
  | { kind: "failed"; message: string };

export interface QueueItem {
  key: string;
  file: File;
  state: ItemState;
}

export type QueueAction =
  | { type: "add"; files: File[]; makeKey?: () => string }
  | { type: "remove"; key: string }
  | { type: "set"; key: string; state: ItemState }
  | { type: "retry"; key: string }
  | { type: "clearFinished" };

const MB = 1024 * 1024;

export function formatSize(bytes: number): string {
  if (bytes >= 1024 * MB) return `${(bytes / (1024 * MB)).toFixed(2)} GB`;
  if (bytes >= 100 * MB) return `${Math.round(bytes / MB)} MB`;
  if (bytes >= MB) return `${(bytes / MB).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Why a file cannot be uploaded, in plain words; null when it can. */
export function checkFile(file: File): string | null {
  const extension = file.name.includes(".") ? (file.name.split(".").pop()?.toLowerCase() ?? "") : "";
  const known = (ACCEPTED_EXTENSIONS as readonly string[]).includes(extension);
  if (!known && !file.type.startsWith("audio/") && file.type !== "video/mp4") {
    return "This is not an audio or video file Sabha can read. Use MP3, M4A, WAV, OGG, WEBM or MP4.";
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_HASH_BYTES) {
    return `Larger than ${formatSize(MAX_HASH_BYTES)}. Split it, or export it as MP3, which is much smaller.`;
  }
  return null;
}

let counter = 0;
const nextKey = () => `f${++counter}`;

export function queueReducer(items: QueueItem[], action: QueueAction): QueueItem[] {
  switch (action.type) {
    case "add": {
      const makeKey = action.makeKey ?? nextKey;
      // The same file picked twice (name, size and date) is listed once.
      const seen = new Set(items.map((i) => `${i.file.name}|${i.file.size}|${i.file.lastModified}`));
      const added: QueueItem[] = [];
      for (const file of action.files) {
        const id = `${file.name}|${file.size}|${file.lastModified}`;
        if (seen.has(id)) continue;
        seen.add(id);
        const reason = checkFile(file);
        added.push({ key: makeKey(), file, state: reason ? { kind: "invalid", reason } : { kind: "ready" } });
      }
      return [...items, ...added];
    }
    case "remove":
      return items.filter((i) => i.key !== action.key || i.state.kind === "uploading");
    case "set":
      return items.map((i) => (i.key === action.key ? { ...i, state: action.state } : i));
    case "retry":
      return items.map((i) =>
        i.key === action.key && i.state.kind === "failed" ? { ...i, state: { kind: "ready" } } : i,
      );
    case "clearFinished":
      return items.filter((i) => i.state.kind !== "done");
  }
}

export interface QueueSummary {
  ready: number;
  uploading: number;
  done: number;
  attention: number;
}

export function summarise(items: readonly QueueItem[]): QueueSummary {
  const summary = { ready: 0, uploading: 0, done: 0, attention: 0 };
  for (const { state } of items) {
    if (state.kind === "ready") summary.ready += 1;
    else if (state.kind === "uploading") summary.uploading += 1;
    else if (state.kind === "done") summary.done += 1;
    else summary.attention += 1;
  }
  return summary;
}

/** "2 uploaded, 1 uploading, 1 needs attention" (Upload.dc.html:96), leaving out the zeros. */
export function summaryText(summary: QueueSummary): string {
  const parts = [
    summary.done && `${summary.done} uploaded`,
    summary.uploading && `${summary.uploading} uploading`,
    summary.ready && `${summary.ready} ready`,
    summary.attention && `${summary.attention} ${summary.attention === 1 ? "needs" : "need"} attention`,
  ].filter(Boolean);
  return parts.join(", ");
}
