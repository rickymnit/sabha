export type ScoreBand = "low" | "mid" | "good";

/**
 * Score colour band, using the report-screen rule (Analysis.dc.html:274-278), chosen over the overview's
 * 3.5 cut-off (Main.dc.html:233-239): below 3 is low, 3 to 3.99 is mid, 4 and above is good.
 * See docs/design/tokens.md "Score colour bands".
 */
export function scoreBand(score: number): ScoreBand {
  if (score < 3) return "low";
  if (score < 4) return "mid";
  return "good";
}
