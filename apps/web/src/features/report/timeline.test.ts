import { describe, expect, it } from "vitest";

import type { Utterance } from "../transcript";
import { formatDuration, formatIst, formatMetricValue, formatMinutes, formatRange, joinList } from "./format";
import { buildBars, evidenceLines, percentAt, talkShares, ticks } from "./timeline";

const u = (role: string, start_ms: number, end_ms: number): Utterance => ({
  role,
  speaker_label: role === "teacher" ? "SPEAKER_00" : "SPEAKER_01",
  start_ms,
  end_ms,
  text: `${role} ${start_ms}`,
  avg_confidence: 0.9,
  low_confidence_spans: [],
});

describe("buildBars", () => {
  const utterances = [u("teacher", 0, 9_000), u("students", 10_000, 19_000), u("teacher", 30_000, 40_000)];

  it("colours each bar by the role that spoke most, and greys removed silence", () => {
    const bars = buildBars(utterances, [{ start_ms: 20_000, end_ms: 30_000 }], 40_000, 4);
    expect(bars.map((b) => b.kind)).toEqual(["speech", "speech", "silence", "speech"]);
    expect(bars.map((b) => b.role)).toEqual(["teacher", "students", undefined, "teacher"]);
    expect(bars[0]!.speech).toBeCloseTo(0.9);
    expect(bars[3]!.speech).toBe(1);
  });

  it("marks a bar with no speech and no removed silence as quiet", () => {
    const bars = buildBars(utterances, [], 40_000, 4);
    expect(bars[2]!.kind).toBe("quiet");
  });

  it("returns nothing for an empty recording", () => {
    expect(buildBars(utterances, [], 0, 10)).toEqual([]);
  });
});

describe("timeline helpers", () => {
  it("talkShares sums speech time per role", () => {
    const shares = talkShares([u("teacher", 0, 3_000), u("students", 3_000, 4_000)]);
    expect(shares).toEqual([
      { role: "teacher", share: 0.75 },
      { role: "students", share: 0.25 },
    ]);
  });

  it("ticks every 10 minutes for a 52-minute recording, without crowding the end", () => {
    expect(ticks(52 * 60_000 + 14_000)).toEqual([0, 10, 20, 30, 40, 50].map((m) => m * 60_000).slice(0, 5));
    expect(ticks(2 * 60_000)).toEqual([0, 60_000]);
  });

  it("percentAt clamps", () => {
    expect(percentAt(-5, 100)).toBe(0);
    expect(percentAt(50, 100)).toBe(50);
    expect(percentAt(500, 100)).toBe(100);
  });

  it("evidenceLines maps quotes to the lines they come from, by time", () => {
    const lines = [u("teacher", 0, 1_000), u("students", 1_000, 2_000), u("teacher", 2_500, 4_000)];
    const map = evidenceLines(lines, [
      { quote: "a", utterance_id: "u0002", start_ms: 2_500, end_ms: 4_000 },
      { quote: "b", utterance_id: "u0000", start_ms: 0, end_ms: 1_000 },
      { quote: "c", utterance_id: "u0002", start_ms: 2_500, end_ms: 4_000 },
    ]);
    expect([...map.entries()].sort()).toEqual([
      [0, [2]],
      [2, [1, 3]],
    ]);
  });
});

describe("format", () => {
  it("shows dates in India Standard Time", () => {
    expect(formatIst("2026-10-13T04:35:00Z")).toBe("13 Oct 2026, 10:05 am");
    expect(formatIst("2026-10-13T20:00:00Z")).toBe("14 Oct 2026, 1:30 am");
    expect(formatIst("nonsense")).toBe("");
  });

  it("formats durations, lists and metric values", () => {
    expect(formatMinutes(38 * 60_000 + 20_000)).toBe("38 min");
    expect(formatMinutes(45_000)).toBe("45 s");
    expect(formatDuration(440_000)).toBe("7 min 20 s");
    expect(formatDuration(120_000)).toBe("2 min");
    expect(joinList(["Hindi"])).toBe("Hindi");
    expect(joinList(["Hindi", "Marathi", "English"])).toBe("Hindi, Marathi and English");
    expect(formatMetricValue({ value: 0.16, unit: "ratio" })).toBe("16%");
    expect(formatMetricValue({ value: 11, unit: "count" })).toBe("11");
    expect(formatMetricValue({ value: 137.6, unit: "wpm" })).toBe("138 wpm");
    expect(formatMetricValue({ value: 440_000, unit: "ms" })).toBe("7 min 20 s");
    expect(formatMetricValue({ value: null, unit: "count" })).toBeNull();
    expect(formatRange({ start_ms: 680_000, end_ms: 1_120_000 })).toBe("11:20 to 18:40");
  });
});
