import { describe, expect, it } from "vitest";

import { lineAt } from "../transcript";
import { mockLesson, mockReport, overallScore, removedSilence, utteranceId } from "./mock";
import type { VerifiedDimension } from "./types";

const lesson = mockLesson();
const utterances = lesson.transcript.utterances;

describe("mock report", () => {
  it("is a 52-minute photosynthesis lesson with speech time net of removed silence", () => {
    expect(lesson.recording.duration_ms).toBeGreaterThanOrEqual(52 * 60_000 + 14_000);
    expect(lesson.recording.duration_ms).toBeGreaterThanOrEqual(utterances[utterances.length - 1]!.end_ms);
    expect(utterances.some((u) => u.text.includes("light reaction"))).toBe(true);
    expect(utterances.some((u) => u.text.includes("Fractions"))).toBe(false);
    const silent = lesson.recording.removed_silence.reduce((sum, r) => sum + r.end_ms - r.start_ms, 0);
    expect(lesson.recording.speech_ms).toBe(lesson.recording.duration_ms - silent);
  });

  it("never removes silence that overlaps speech", () => {
    for (const range of lesson.recording.removed_silence) {
      for (const u of utterances) expect(u.end_ms <= range.start_ms || u.start_ms >= range.end_ms).toBe(true);
    }
  });

  it.each(["completed", "no-comparison", "partial"] as const)(
    "%s: every quote is text of the utterance it names, at that utterance's times",
    (variant) => {
      const report = mockReport(lesson, variant);
      const quotes = report.dimensions.flatMap((d) => (d.verified ? d.evidence : []));
      expect(quotes.length).toBeGreaterThan(0);
      for (const q of quotes) {
        const index = lineAt(utterances, q.start_ms);
        const u = utterances[index]!;
        expect(utteranceId(index)).toBe(q.utterance_id);
        expect(u.start_ms).toBe(q.start_ms);
        expect(u.end_ms).toBe(q.end_ms);
        expect(u.text).toContain(q.quote);
      }
      expect(report.suggestions).toHaveLength(3);
      for (const s of report.suggestions) {
        const index = lineAt(utterances, s.start_ms);
        expect(utteranceId(index)).toBe(s.utterance_id);
        expect(utterances[index]!.start_ms).toBe(s.start_ms);
      }
    },
  );

  it("counts the metrics from the transcript", () => {
    const report = mockReport(lesson);
    const byKey = Object.fromEntries(report.metrics.map((m) => [m.key, m]));
    // Same rule as the metric's definition: turns by the teacher that contain a question.
    const questions = utterances.filter((u) => u.role === "teacher" && u.text.includes("?")).length;
    expect(byKey.teacher_question_count?.value).toBe(questions);
    const share = byKey.student_talk_share?.value ?? -1;
    expect(share).toBeGreaterThan(0);
    expect(share).toBeLessThan(0.5);
    const longest = byKey.longest_monologue_ms!;
    expect(longest.value).toBe(longest.range!.end_ms - longest.range!.start_ms);
  });

  it("computes the overall score from verified dimensions only", () => {
    const full = mockReport(lesson);
    const partial = mockReport(lesson, "partial");
    expect(full.overall).toBe(overallScore(full.dimensions));
    expect(partial.status).toBe("partial");
    expect(partial.dimensions.filter((d) => !d.verified).map((d) => d.key)).toEqual(["pacing", "recap_and_closure"]);
    const verified = partial.dimensions.filter((d): d is VerifiedDimension => d.verified);
    const weight = verified.reduce((s, d) => s + d.weight, 0);
    const mean = verified.reduce((s, d) => s + d.score * d.weight, 0) / weight;
    expect(partial.overall).toBe(Math.round(mean * 10) / 10);
    expect(mockReport(lesson, "no-comparison").comparison).toBeNull();
  });

  it("gives no overall score under 60% verified weight", () => {
    const dims = mockReport(lesson).dimensions.map((d, i) =>
      i < 3 ? { key: d.key, name: d.name, weight: d.weight, verified: false as const } : d,
    );
    expect(overallScore(dims)).toBeNull();
  });
});

describe("removedSilence", () => {
  it("keeps long gaps (minus padding), the lead-in and the tail", () => {
    const u = (start_ms: number, end_ms: number) => ({
      role: "teacher",
      speaker_label: "SPEAKER_00",
      start_ms,
      end_ms,
      text: "x",
      avg_confidence: 1,
      low_confidence_spans: [],
    });
    expect(removedSilence([u(3_000, 5_000), u(5_500, 7_000), u(12_000, 13_000)], 20_000)).toEqual([
      { start_ms: 0, end_ms: 2_750 },
      { start_ms: 7_250, end_ms: 11_750 },
      { start_ms: 13_250, end_ms: 20_000 },
    ]);
  });
});
