// Pure helpers for the report timeline: speech bars by role, removed silence, time ticks, talk share, and which
// transcript lines a dimension's evidence points at. Everything is on the ORIGINAL recording timeline.

import { lineAt, type Utterance } from "../transcript";
import type { EvidenceQuote, TimeRange } from "./types";

export type BarKind = "speech" | "silence" | "quiet";

export interface Bar {
  kind: BarKind;
  /** Role with the most speech in the bar (speech bars only). */
  role?: string;
  /** Share of the bar's time that is speech, 0 to 1. */
  speech: number;
  /** Drawn height in px. */
  height: number;
}

const overlap = (a0: number, a1: number, b0: number, b1: number) => Math.max(0, Math.min(a1, b1) - Math.max(a0, b0));

/** Same-shape texture for every recording so the bars read as a waveform. Decorative only: there is no loudness data. */
const texture = (i: number) => 0.55 + 0.45 * Math.abs(Math.sin(i * 0.61) * Math.cos(i * 0.23));

export const BAR_MAX_PX = 44;
export const BAR_MIN_PX = 4;

/**
 * Splits the recording into `count` equal bars. A bar that is mostly removed silence is "silence" (grey); one with
 * no speech is "quiet"; otherwise it takes the colour of the role that spoke most in it. Height grows with the
 * share of the bar that is speech; the texture on top is decorative.
 */
export function buildBars(
  utterances: readonly Utterance[],
  removedSilence: readonly TimeRange[],
  durationMs: number,
  count: number,
): Bar[] {
  if (durationMs <= 0 || count <= 0) return [];
  const width = durationMs / count;
  const bars: Bar[] = [];
  let u = 0;
  let s = 0;
  for (let i = 0; i < count; i++) {
    const from = i * width;
    const to = from + width;
    while (u < utterances.length && (utterances[u] as Utterance).end_ms <= from) u++;
    while (s < removedSilence.length && (removedSilence[s] as TimeRange).end_ms <= from) s++;

    let silent = 0;
    for (let j = s; j < removedSilence.length && (removedSilence[j] as TimeRange).start_ms < to; j++) {
      const r = removedSilence[j] as TimeRange;
      silent += overlap(from, to, r.start_ms, r.end_ms);
    }
    const byRole = new Map<string, number>();
    let speech = 0;
    for (let j = u; j < utterances.length && (utterances[j] as Utterance).start_ms < to; j++) {
      const utt = utterances[j] as Utterance;
      const ms = overlap(from, to, utt.start_ms, utt.end_ms);
      if (ms <= 0) continue;
      speech += ms;
      byRole.set(utt.role, (byRole.get(utt.role) ?? 0) + ms);
    }
    const share = Math.min(1, speech / width);
    if (silent >= width / 2) {
      bars.push({ kind: "silence", speech: share, height: BAR_MIN_PX });
    } else if (speech === 0) {
      bars.push({ kind: "quiet", speech: 0, height: BAR_MIN_PX });
    } else {
      let role = "";
      let best = -1;
      for (const [r, ms] of byRole) {
        if (ms > best) {
          best = ms;
          role = r;
        }
      }
      const height = Math.round(BAR_MIN_PX + 6 + (BAR_MAX_PX - BAR_MIN_PX - 6) * share * texture(i));
      bars.push({ kind: "speech", role, speech: share, height });
    }
  }
  return bars;
}

/** Each role's share of all speech time, 0 to 1, in order of first appearance. */
export function talkShares(utterances: readonly Utterance[]): { role: string; share: number }[] {
  const totals = new Map<string, number>();
  let all = 0;
  for (const u of utterances) {
    const ms = Math.max(0, u.end_ms - u.start_ms);
    totals.set(u.role, (totals.get(u.role) ?? 0) + ms);
    all += ms;
  }
  return [...totals].map(([role, ms]) => ({ role, share: all > 0 ? ms / all : 0 }));
}

export function totalMs(ranges: readonly TimeRange[]): number {
  return ranges.reduce((sum, r) => sum + Math.max(0, r.end_ms - r.start_ms), 0);
}

const TICK_STEPS_MIN = [1, 2, 5, 10, 15, 20, 30, 60, 120];

/** Tick times for the axis: the smallest round step giving at most `maxTicks` inner ticks, plus 0. */
export function ticks(durationMs: number, maxTicks = 5): number[] {
  if (durationMs <= 0) return [0];
  const stepMin = TICK_STEPS_MIN.find((m) => durationMs / (m * 60_000) <= maxTicks + 1) ?? 240;
  const step = stepMin * 60_000;
  const result: number[] = [];
  // Leave out an inner tick that would crowd the end label.
  for (let t = 0; t <= durationMs - step * 0.4; t += step) result.push(t);
  return result;
}

/** Position on the timeline as a CSS percentage, clamped to [0, 100]. */
export function percentAt(ms: number, durationMs: number): number {
  if (durationMs <= 0) return 0;
  return Math.min(100, Math.max(0, (ms / durationMs) * 100));
}

/**
 * Transcript lines each quote comes from, as line index → 1-based evidence numbers. Lines are found by time (the
 * utterance playing at the quote's start, plus any that start before it ends), so the UI does not depend on the
 * utterance id format.
 */
export function evidenceLines(
  utterances: readonly Utterance[],
  evidence: readonly EvidenceQuote[],
): Map<number, number[]> {
  const lines = new Map<number, number[]>();
  evidence.forEach((quote, i) => {
    const first = lineAt(utterances, quote.start_ms);
    if (first < 0) return;
    for (let line = first; line < utterances.length; line++) {
      const u = utterances[line] as Utterance;
      if (line > first && u.start_ms >= quote.end_ms) break;
      const numbers = lines.get(line) ?? [];
      if (!numbers.includes(i + 1)) numbers.push(i + 1);
      lines.set(line, numbers);
    }
  });
  return lines;
}
