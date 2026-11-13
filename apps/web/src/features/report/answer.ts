// The report's answer first (ReportAnswer): the agreed next step whatever the kind of conversation, and the best and
// lowest verified rubric points. Plain functions so they can be tested.

import { formatScore } from "./format";
import { displayedScore, type AnalysisReport, type VerifiedDimension } from "./types";

const OWNER: Record<string, string> = {
  sales_rep: "The rep",
  support_agent: "The agent",
  customer: "The customer",
  both: "Both sides",
};

export interface Step {
  text: string;
  who: string | null;
  when: string | null;
  ms: number | null;
}

/** The agreed next step, whatever kind of conversation this was; null when none was agreed. */
export function nextStep(analysis: AnalysisReport): Step | null {
  const deal = analysis.deal_card?.next_step;
  if (deal) return { text: deal.action, who: OWNER[deal.owner] ?? null, when: deal.due, ms: deal.evidence.start_ms };
  const follow = analysis.case_card?.follow_up;
  if (follow) {
    return { text: follow.action, who: OWNER[follow.owner] ?? null, when: follow.due, ms: follow.evidence.start_ms };
  }
  const ticket = analysis.ticket?.follow_up;
  if (ticket)
    return { text: ticket.text, who: null, when: null, ms: analysis.ticket?.evidence.outcome.start_ms ?? null };
  const item = analysis.meeting_notes?.action_items[0];
  if (item) return { text: item.action, who: item.owner, when: item.due, ms: item.evidence.start_ms };
  return null;
}

/** The best and the lowest verified rubric points; "went well" only when it is better than the lowest. */
export function bestAndWorst(dimensions: readonly VerifiedDimension[]): {
  best: VerifiedDimension | null;
  worst: VerifiedDimension | null;
} {
  if (dimensions.length === 0) return { best: null, worst: null };
  const sorted = [...dimensions].sort((a, b) => displayedScore(a) - displayedScore(b));
  const worst = sorted[0]!;
  const best = sorted.at(-1)!;
  return {
    worst: displayedScore(worst) < 4 ? worst : null,
    best: displayedScore(best) > displayedScore(worst) || displayedScore(best) >= 4 ? best : null,
  };
}

/** Where this score sits in the person's recent range: "Lowest of Rohit's last 21 conversations (range 1.6 to 4.2)." */
export function historyText(overall: number, history: AnalysisReport["person_history"], name: string, plural: string) {
  if (!history || history.count === 0) return null;
  const count = history.count + 1;
  const min = Math.min(history.min, overall);
  const max = Math.max(history.max, overall);
  const range = `range ${formatScore(min)} to ${formatScore(max)}`;
  if (overall <= history.min) return `Lowest of ${name}’s last ${count} ${plural} (${range}).`;
  if (overall >= history.max) return `Highest of ${name}’s last ${count} ${plural} (${range}).`;
  return `${name}’s last ${count} ${plural}: ${range}.`;
}
