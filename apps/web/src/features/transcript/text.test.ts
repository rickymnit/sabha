import { describe, expect, it } from "vitest";

import { findMatches, formatClock, formatSpoken, lineAt, segmentText, toUtf16Range } from "./text";
import type { Utterance } from "./types";

const u = (start_ms: number, text = "x", extra: Partial<Utterance> = {}): Utterance => ({
  role: "teacher",
  speaker_label: "SPEAKER_00",
  start_ms,
  end_ms: start_ms + 1000,
  text,
  avg_confidence: 0.9,
  low_confidence_spans: [],
  ...extra,
});

describe("formatClock", () => {
  it("shows m:ss under an hour and h:mm:ss above", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(1_265_999)).toBe("21:05");
    expect(formatClock(3_600_000 + 5 * 60_000 + 9_000)).toBe("1:05:09");
    expect(formatClock(-5)).toBe("0:00");
    expect(formatClock(Number.NaN)).toBe("0:00");
  });
});

describe("formatSpoken", () => {
  it("uses words with singular and plural units", () => {
    expect(formatSpoken(0)).toBe("0 seconds");
    expect(formatSpoken(61_000)).toBe("1 minute 1 second");
    expect(formatSpoken(3 * 3_600_000)).toBe("3 hours");
    expect(formatSpoken(3_600_000 + 2_000)).toBe("1 hour 2 seconds");
  });
});

describe("lineAt", () => {
  const lines = [u(1_000), u(5_000), u(9_000)];
  it("returns the last line that has started", () => {
    expect(lineAt(lines, 0)).toBe(-1);
    expect(lineAt(lines, 1_000)).toBe(0);
    expect(lineAt(lines, 4_999)).toBe(0); // in the pause after line 0
    expect(lineAt(lines, 5_000)).toBe(1);
    expect(lineAt(lines, 99_000)).toBe(2);
    expect(lineAt([], 10)).toBe(-1);
  });
});

describe("toUtf16Range", () => {
  it("is the identity without astral characters, Devanagari included", () => {
    expect(toUtf16Range("नमस्ते class", 7, 12)).toEqual([7, 12]);
  });
  it("converts code points to UTF-16 units around astral characters", () => {
    const text = "😀 ok 😀 yes";
    const [start, end] = toUtf16Range(text, 7, 10);
    expect(text.slice(start, end)).toBe("yes");
  });
});

describe("findMatches", () => {
  const lines = [u(0, "Stomata open by day."), u(1, "No match here"), u(2, "STOMATA, stomata!")];
  it("finds every case-insensitive hit in reading order", () => {
    expect(findMatches(lines, "stomata")).toEqual([
      { line: 0, start: 0, end: 7 },
      { line: 2, start: 0, end: 7 },
      { line: 2, start: 9, end: 16 },
    ]);
  });
  it("treats the query literally and ignores blank queries", () => {
    expect(findMatches([u(0, "a.b axb")], "a.b")).toEqual([{ line: 0, start: 0, end: 3 }]);
    expect(findMatches(lines, "   ")).toEqual([]);
  });
});

describe("segmentText", () => {
  it("returns the whole text when nothing is marked", () => {
    expect(segmentText("hello", [], [])).toEqual([{ text: "hello" }]);
  });
  it("splits overlapping low-confidence spans and matches", () => {
    const span = [4, 11] as const;
    const segments = segmentText("Sab samajh aaya?", [span], [{ start: 0, end: 7 }]);
    expect(segments).toEqual([
      { text: "Sab ", match: 0 },
      { text: "sam", lowConfidence: span, match: 0 },
      { text: "ajh ", lowConfidence: span },
      { text: "aaya?" },
    ]);
  });
});
