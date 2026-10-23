import { describe, expect, it } from "vitest";

import { checkFile, formatSize, queueReducer, summarise, summaryText, type QueueItem } from "./queue";
import { MAX_HASH_BYTES } from "./upload";

const audio = (name = "Class 7B.mp3", size = 10) => {
  const file = new File(["x".repeat(Math.min(size, 10))], name, { type: name.endsWith(".mp3") ? "audio/mpeg" : "" });
  Object.defineProperty(file, "size", { value: size });
  return file;
};

describe("checkFile", () => {
  it("accepts audio and video by extension or type", () => {
    expect(checkFile(audio())).toBeNull();
    expect(checkFile(audio("Front desk.M4A"))).toBeNull();
    expect(checkFile(new File(["x"], "recording", { type: "audio/x-wav" }))).toBeNull();
  });

  it("says in plain words why a file cannot go up", () => {
    expect(checkFile(new File(["x"], "notes.txt", { type: "text/plain" }))).toMatch(/not an audio or video file/);
    expect(checkFile(audio("empty.mp3", 0))).toBe("This file is empty.");
    expect(checkFile(audio("Annual day.wav", MAX_HASH_BYTES + 1))).toMatch(/^Larger than 512 MB\. Split it/);
  });
});

describe("formatSize", () => {
  it("reads like a file manager", () => {
    expect(formatSize(431 * 1024)).toBe("431 KB");
    expect(formatSize(13.2 * 1024 * 1024)).toBe("13.2 MB");
    expect(formatSize(512 * 1024 * 1024)).toBe("512 MB");
    expect(formatSize(1.5 * 1024 ** 3)).toBe("1.50 GB");
  });
});

describe("queueReducer", () => {
  let n = 0;
  const makeKey = () => `k${++n}`;

  it("adds files once each, checking them as they arrive", () => {
    const a = audio("a.mp3");
    let items = queueReducer([], { type: "add", files: [a, new File(["x"], "b.txt")], makeKey });
    items = queueReducer(items, { type: "add", files: [a], makeKey }); // picked again: still once
    expect(items.map((i) => [i.file.name, i.state.kind])).toEqual([
      ["a.mp3", "ready"],
      ["b.txt", "invalid"],
    ]);
  });

  it("never drops a file while it is uploading, and retries only failures", () => {
    const [item] = queueReducer([], { type: "add", files: [audio()], makeKey }) as [QueueItem];
    let items = queueReducer([item], { type: "set", key: item.key, state: { kind: "uploading", sent: 1, total: 10 } });
    items = queueReducer(items, { type: "remove", key: item.key });
    expect(items).toHaveLength(1);
    items = queueReducer(items, { type: "retry", key: item.key });
    expect(items[0]?.state.kind).toBe("uploading");
    items = queueReducer(items, { type: "set", key: item.key, state: { kind: "failed", message: "x" } });
    expect(queueReducer(items, { type: "retry", key: item.key })[0]?.state.kind).toBe("ready");
  });

  it("summarises the list the way the design does", () => {
    const states: QueueItem["state"][] = [
      { kind: "done", recordingId: "r1", awaitingConsent: false },
      { kind: "uploading", sent: 1, total: 2 },
      { kind: "invalid", reason: "x" },
      { kind: "failed", message: "x" },
    ];
    const items = states.map((state, i) => ({ key: `s${i}`, file: audio(), state }));
    expect(summaryText(summarise(items))).toBe("1 uploaded, 1 uploading, 2 need attention");
  });
});
