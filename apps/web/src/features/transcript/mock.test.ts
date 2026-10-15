import { describe, expect, it } from "vitest";

import { generateMockTranscript } from "./mock";

describe("generateMockTranscript", () => {
  it("is deterministic for a seed", () => {
    expect(generateMockTranscript({ lines: 50, seed: 3 })).toEqual(generateMockTranscript({ lines: 50, seed: 3 }));
    expect(generateMockTranscript({ lines: 50, seed: 3 })).not.toEqual(generateMockTranscript({ lines: 50, seed: 4 }));
  });

  it("produces exactly the requested number of lines, 5,000 included", () => {
    const { utterances } = generateMockTranscript({ lines: 5_000 });
    expect(utterances).toHaveLength(5_000);
  });

  it("covers a 3-hour recording by default with valid, sorted, non-overlapping utterances", () => {
    const transcript = generateMockTranscript();
    const { utterances } = transcript;
    expect(transcript.version).toBe("transcript@v1");
    expect(transcript.timeline).toBe("original");
    expect(transcript.word_count).toBeGreaterThan(utterances.length);
    const last = utterances[utterances.length - 1];
    expect(last?.end_ms).toBeGreaterThanOrEqual(3 * 3_600_000);
    expect(last?.start_ms).toBeLessThan(3 * 3_600_000);

    let previousEnd = 0;
    for (const u of utterances) {
      expect(u.start_ms).toBeGreaterThanOrEqual(previousEnd);
      expect(u.end_ms).toBeGreaterThan(u.start_ms);
      expect(["teacher", "students"]).toContain(u.role);
      expect(u.speaker_label).toMatch(/^SPEAKER_\d\d$/);
      expect(u.avg_confidence).toBeGreaterThan(0);
      expect(u.avg_confidence).toBeLessThanOrEqual(1);
      const length = Array.from(u.text).length;
      for (const [start, end] of u.low_confidence_spans) {
        expect(start).toBeGreaterThanOrEqual(0);
        expect(end).toBeLessThanOrEqual(length);
        expect(end).toBeGreaterThan(start);
      }
      previousEnd = u.end_ms;
    }
    expect(utterances.some((u) => u.low_confidence_spans.length > 0)).toBe(true);
    expect(utterances.some((u) => u.role === "students")).toBe(true);
  });
});
