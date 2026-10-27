// Pure maths for SpeakerStrip: speaker turns (ms on the ORIGINAL recording timeline) to positioned spans, and the
// staff member's share of the speech.

export type SpeakerKind = "staff" | "other";

export interface SpeakerSegment {
  start_ms: number;
  end_ms: number;
  speaker: SpeakerKind;
}

export interface SpeakerSpan {
  speaker: SpeakerKind;
  /** Left edge and width, in percent of the recording. */
  left: number;
  width: number;
}

/**
 * Positions each turn on the recording, clamped to [0, durationMs]. Neighbouring turns of the same speaker closer
 * than `mergeGapPct` percent are drawn as one span, so a 140px row shows a readable pattern rather than hundreds of
 * slivers; the gaps that remain are silence or the other side.
 */
export function speakerSpans(segments: readonly SpeakerSegment[], durationMs: number, mergeGapPct = 0): SpeakerSpan[] {
  if (durationMs <= 0) return [];
  const pct = (ms: number) => (Math.min(durationMs, Math.max(0, ms)) / durationMs) * 100;
  const sorted = [...segments].sort((a, b) => a.start_ms - b.start_ms);
  const spans: SpeakerSpan[] = [];
  for (const seg of sorted) {
    const left = pct(seg.start_ms);
    const right = pct(seg.end_ms);
    if (right <= left) continue;
    const last = spans.at(-1);
    if (last && last.speaker === seg.speaker && left - (last.left + last.width) <= mergeGapPct) {
      last.width = Math.max(last.width, right - last.left);
    } else {
      spans.push({ speaker: seg.speaker, left, width: right - left });
    }
  }
  return spans;
}

/** The staff member's share of all speech, 0 to 1, or null when nobody spoke. Overlapping talk counts for both. */
export function staffShare(segments: readonly SpeakerSegment[]): number | null {
  let staff = 0;
  let total = 0;
  for (const seg of segments) {
    const ms = Math.max(0, seg.end_ms - seg.start_ms);
    total += ms;
    if (seg.speaker === "staff") staff += ms;
  }
  return total > 0 ? staff / total : null;
}
