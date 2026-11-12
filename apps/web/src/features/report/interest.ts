// Interest levels as users see them (deal card, the rep's interactions and next actions).

export type Tone = "neutral" | "good" | "warn" | "bad";
// The words are the sales rubric's output_labels when given (v0.4 on); these match them for older rubrics.
const INTEREST: Record<string, { text: string; tone: Tone }> = {
  high: { text: "Interested", tone: "good" },
  medium: { text: "Considering", tone: "warn" },
  low: { text: "Not interested", tone: "bad" },
  unclear: { text: "Unclear", tone: "neutral" },
};

/** What users see for an interest level: the rubric's label if it has one, with the level's colour. */
export function interestView(value: string, labels?: Record<string, string>): { text: string; tone: Tone } {
  const base = INTEREST[value] ?? INTEREST.unclear ?? { text: value, tone: "neutral" };
  return { ...base, text: labels?.[value] ?? base.text };
}
