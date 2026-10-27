export type ScoreBand = "low" | "mid" | "good";

/**
 * Score colour band, UI v2 rule (docs/design/v2/01-overview.png, the coaching legend): below 3.0 is low,
 * 3.0 to 3.7 is mid, 3.8 and above is good. The cut is on the one-decimal value people see, so 3.75 (shown as 3.8)
 * is good. See docs/design/tokens.md "Score colour bands".
 */
export function scoreBand(score: number): ScoreBand {
  const shown = Math.round(score * 10) / 10;
  if (shown < 3) return "low";
  if (shown < 3.8) return "mid";
  return "good";
}
