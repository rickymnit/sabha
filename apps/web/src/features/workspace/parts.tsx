// Small pieces shared by the sales rep's own workspace (founder's Sales Executive dashboard doc, 2026-11-12): the
// call or meeting chip, the AI-suggested interest, a next action's priority and due date.

import { Icon, cx } from "../../design";
import { interestView, type Tone } from "../report/interest";

const TONE: Record<Tone, string> = {
  good: "bg-success-tint text-success",
  warn: "bg-warning-tint text-warning-ink",
  bad: "bg-danger-tint text-danger",
  neutral: "bg-fill text-muted",
};

export function InteractionChip({ kind }: { kind: "call" | "meeting" | null | undefined }) {
  const call = kind === "call";
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary-tint-subtle px-2 py-0.5 text-caption font-semibold text-primary-hover">
      <Icon name={call ? "phone" : "people"} size={13} />
      {call ? "Call" : "Meeting"}
    </span>
  );
}

export function InterestPill({ value, labels }: { value: string | null | undefined; labels?: Record<string, string> }) {
  if (!value) return null;
  const view = interestView(value, labels);
  return (
    <span className={cx("inline-flex shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold", TONE[view.tone])}>
      {view.text}
    </span>
  );
}

const PRIORITY = {
  high: { text: "High", tone: TONE.bad },
  medium: { text: "Medium", tone: TONE.warn },
  low: { text: "Low", tone: TONE.neutral },
} as const;

export function PriorityPill({ priority }: { priority: "high" | "medium" | "low" }) {
  const view = PRIORITY[priority];
  return (
    <span className={cx("inline-flex shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold", view.tone)}>
      {view.text} priority
    </span>
  );
}
