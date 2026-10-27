import { describe, expect, it } from "vitest";

import { speakerSpans, staffShare } from "./speakerSpans";

describe("speakerSpans", () => {
  it("positions turns in percent, clamps to the recording and merges close turns of one speaker", () => {
    const spans = speakerSpans(
      [
        { start_ms: 500, end_ms: 1_000, speaker: "staff" },
        { start_ms: 0, end_ms: 400, speaker: "staff" },
        { start_ms: 1_000, end_ms: 1_500, speaker: "other" },
        { start_ms: 9_000, end_ms: 12_000, speaker: "staff" },
      ],
      10_000,
      1,
    );
    expect(spans).toEqual([
      { speaker: "staff", left: 0, width: 10 },
      { speaker: "other", left: 10, width: 5 },
      { speaker: "staff", left: 90, width: 10 },
    ]);
  });
});

describe("staffShare", () => {
  it("is the staff member's share of speech, or null without speech", () => {
    expect(
      staffShare([
        { start_ms: 0, end_ms: 3_000, speaker: "staff" },
        { start_ms: 3_000, end_ms: 4_000, speaker: "other" },
      ]),
    ).toBe(0.75);
    expect(staffShare([])).toBeNull();
  });
});
