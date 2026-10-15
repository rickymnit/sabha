// Pure helpers for the transcript view: time formatting, finding the current line, search and text segments.

import type { LowConfidenceSpan, Utterance } from "./types";

/** "4:07", "52:14" or "2:05:09". Negative or non-finite input shows as "0:00". */
export function formatClock(ms: number): string {
  const total = Number.isFinite(ms) && ms > 0 ? Math.floor(ms / 1000) : 0;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${ss}` : `${minutes}:${ss}`;
}

const unit = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Words for screen readers: "1 hour 5 minutes 3 seconds", "0 seconds". */
export function formatSpoken(ms: number): string {
  const total = Number.isFinite(ms) && ms > 0 ? Math.floor(ms / 1000) : 0;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const parts: string[] = [];
  if (hours) parts.push(unit(hours, "hour", "hours"));
  if (minutes) parts.push(unit(minutes, "minute", "minutes"));
  if (seconds || parts.length === 0) parts.push(unit(seconds, "second", "seconds"));
  return parts.join(" ");
}

/**
 * Index of the line playing at `ms`: the last utterance that has started (so a pause between turns keeps the
 * previous line lit). -1 before the first utterance. Binary search; utterances are sorted by start_ms.
 */
export function lineAt(utterances: readonly Utterance[], ms: number): number {
  let lo = 0;
  let hi = utterances.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if ((utterances[mid] as Utterance).start_ms <= ms) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

const SURROGATE = /[\uD800-\uDFFF]/;

/** Converts a code-point range (how the API counts) into a UTF-16 range (how JavaScript strings count). */
export function toUtf16Range(text: string, start: number, end: number): [number, number] {
  if (!SURROGATE.test(text)) return [start, end];
  let codePoint = 0;
  let unitIndex = 0;
  let from = text.length;
  let to = text.length;
  for (const char of text) {
    if (codePoint === start) from = unitIndex;
    if (codePoint === end) {
      to = unitIndex;
      break;
    }
    codePoint += 1;
    unitIndex += char.length;
  }
  return [Math.min(from, to), to];
}

/** One search hit: `line` is the utterance index, `start`/`end` UTF-16 offsets into its text. */
export interface Match {
  line: number;
  start: number;
  end: number;
}

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Case-insensitive, literal search across every line, in reading order. Blank queries match nothing. */
export function findMatches(utterances: readonly Utterance[], query: string): Match[] {
  const needle = query.trim();
  if (!needle) return [];
  const pattern = new RegExp(escapeRegExp(needle), "giu");
  const matches: Match[] = [];
  utterances.forEach((utterance, line) => {
    for (const hit of utterance.text.matchAll(pattern)) {
      matches.push({ line, start: hit.index, end: hit.index + hit[0].length });
    }
  });
  return matches;
}

/** A run of text with the same styling. */
export interface Segment {
  text: string;
  /** Set when the run is inside a low-confidence span. */
  lowConfidence?: LowConfidenceSpan;
  /** Index into the line's matches when the run is a search hit. */
  match?: number;
}

/**
 * Splits a line into runs so low-confidence spans and search hits can both be marked, even where they overlap.
 * `matches` are UTF-16 ranges for this line only, in order.
 */
export function segmentText(
  text: string,
  spans: readonly LowConfidenceSpan[],
  matches: readonly { start: number; end: number }[],
): Segment[] {
  const low = spans
    .map((span) => {
      const [start, end] = toUtf16Range(text, span[0], span[1]);
      return { start: Math.max(0, start), end: Math.min(text.length, end), span };
    })
    .filter((s) => s.end > s.start);
  if (low.length === 0 && matches.length === 0) return [{ text }];

  const cuts = new Set<number>([0, text.length]);
  for (const s of low) cuts.add(s.start).add(s.end);
  for (const m of matches) cuts.add(m.start).add(m.end);
  const points = [...cuts].filter((p) => p >= 0 && p <= text.length).sort((a, b) => a - b);

  const segments: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i] as number;
    const to = points[i + 1] as number;
    if (to <= from) continue;
    const lowConfidence = low.find((s) => s.start <= from && to <= s.end)?.span;
    const matchIndex = matches.findIndex((m) => m.start <= from && to <= m.end);
    segments.push({
      text: text.slice(from, to),
      ...(lowConfidence ? { lowConfidence } : {}),
      ...(matchIndex >= 0 ? { match: matchIndex } : {}),
    });
  }
  return segments;
}
