// Small pieces shared by the sales rep's own workspace (founder's Sales Executive dashboard doc, 2026-11-12), built
// to read at a glance (manager's feedback, 2026-11-12): a score says what it means in a word, a call or meeting is a
// quiet label, and only priorities worth acting on get a tag.

import { Icon, cx, scoreBand, scoreWord } from "../../design";
import { interestView, type Tone } from "../report/interest";
import { kindWord } from "./words";

const TONE: Record<Tone, string> = {
  good: "bg-success-tint text-success",
  warn: "bg-warning-tint text-warning-ink",
  bad: "bg-danger-tint text-danger",
  neutral: "bg-fill text-muted",
};

const DOT = { low: "bg-danger-bar", mid: "bg-warning-bar", good: "bg-success-bar" } as const;

/** "Call" or "Meeting" with its icon, in the muted line under a name. */
export function KindLabel({ kind }: { kind: "call" | "meeting" | null | undefined }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1">
      <Icon name={kind === "call" ? "phone" : "people"} size={13} />
      {kindWord(kind)}
    </span>
  );
}

/** A score in words first: "● Needs work 2.2 / 5". `size="lg"` for the Overview and a conversation's page. */
export function ScoreVerdict({ score, size = "sm" }: { score: number | null | undefined; size?: "sm" | "lg" }) {
  if (score == null) return <span className="text-small text-muted">No score yet</span>;
  const band = scoreBand(score);
  return (
    <span className={cx("inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap", size === "lg" && "gap-2")}>
      <span aria-hidden="true" className={cx("rounded-full", DOT[band], size === "lg" ? "h-2.5 w-2.5" : "h-2 w-2")} />
      <span className={cx("font-semibold text-ink", size === "lg" ? "text-lg" : "text-sm")}>{scoreWord(score)}</span>
      <span className={cx("tabular-nums text-muted", size === "lg" ? "text-sm" : "text-small")}>
        {score.toFixed(1)} / 5
      </span>
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
  high: { text: "Do first", tone: TONE.bad },
  medium: { text: "This week", tone: TONE.warn },
} as const;

/** A tag only for actions worth doing soon; the rest need no label. */
export function PriorityPill({ priority }: { priority: "high" | "medium" | "low" }) {
  if (priority === "low") return null;
  const view = PRIORITY[priority];
  return (
    <span className={cx("inline-flex shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold", view.tone)}>
      {view.text}
    </span>
  );
}
