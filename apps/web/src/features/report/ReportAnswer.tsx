// The top of a report, read in a few seconds (manager's feedback, 2026-11-13): how it went in a word, the verified
// summary, and three cards: what went well, what needs work and what happens next. Everything here is already in the
// analysis and verified (golden rule 5): the best and the lowest verified rubric points with their reasoning, and the
// next step from the deal card, case card, ticket or meeting notes. "See why" opens the full detail below.

import type { ReactNode } from "react";

import { Icon, cx, scoreBand, scoreWord, type IconName, type ScoreBand } from "../../design";
import { checkedText } from "./format";
import { TimeChip } from "./SalesPanels";
import { bestAndWorst, historyText, momentsSummary, nextStep } from "./answer";
import { displayedScore, type AnalysisReport, type Labels, type VerifiedDimension } from "./types";

const DOT: Record<ScoreBand, string> = { low: "bg-danger-bar", mid: "bg-warning-bar", good: "bg-success-bar" };
const WORD: Record<ScoreBand, string> = { low: "text-danger", mid: "text-warning", good: "text-success" };
function Card({
  tone,
  icon,
  label,
  children,
}: {
  tone: "good" | "work" | "next";
  icon: IconName;
  label: string;
  children: ReactNode;
}) {
  const tones = {
    good: "border-success-tint bg-success-tint/50",
    work: "border-warning-tint bg-warning-tint/50",
    next: "border-primary-tint-strong bg-primary-tint-subtle",
  } as const;
  const ink = { good: "text-success", work: "text-warning-ink", next: "text-primary-hover" } as const;
  return (
    <section
      aria-label={label}
      className={cx("flex min-w-0 flex-col gap-2 rounded-panel border px-5 py-4", tones[tone])}
    >
      <span className={cx("flex items-center gap-1.5 text-small font-bold uppercase tracking-wide", ink[tone])}>
        <Icon name={icon} size={15} /> {label}
      </span>
      {children}
    </section>
  );
}

function Point({ d, onWhy }: { d: VerifiedDimension; onWhy: (key: string) => void }) {
  const score = displayedScore(d);
  const band = scoreBand(score);
  return (
    <>
      <p className="m-0 text-lg font-bold leading-snug text-ink">{d.name}</p>
      <p className="m-0 text-sm">
        <span className={cx("font-semibold", WORD[band])}>{scoreWord(score)}</span>
        <span className="text-muted"> · {score} / 5</span>
      </p>
      <p className="m-0 line-clamp-3 text-sm text-ink-2">{d.rationale}</p>
      <button
        type="button"
        onClick={() => onWhy(d.key)}
        className="mt-auto inline-flex items-center gap-1 self-start bg-transparent p-0 text-sm font-semibold text-primary hover:text-primary-hover"
      >
        See why <Icon name="chevronRight" size={14} />
      </button>
    </>
  );
}

export interface ReportAnswerProps {
  analysis: AnalysisReport;
  dimensions: readonly VerifiedDimension[];
  labels: Labels;
  /** Opens a rubric point's detail below. */
  onWhy: (key: string) => void;
  /** Opens the list of what was said well and badly. */
  onMoments?: () => void;
  /** Plays (or shows) a moment. */
  onSeek: (ms: number) => void;
  /** The person analysed, for "Rohit's last 21 conversations" and the private-coaching note. */
  personName: string;
}

export function ReportAnswer({
  analysis,
  dimensions,
  labels,
  onWhy,
  onMoments,
  onSeek,
  personName,
}: ReportAnswerProps) {
  const firstName = personName.split(" ")[0] ?? personName;
  const history =
    analysis.overall === null
      ? null
      : historyText(analysis.overall, analysis.person_history, firstName, labels.recording_plural.toLowerCase());
  const overall = analysis.overall;
  const band = overall === null ? null : scoreBand(overall);
  const { best, worst } = bestAndWorst(dimensions);
  const step = nextStep(analysis);
  const recording = labels.recording.toLowerCase();
  return (
    <section aria-label="In short" className="flex flex-col gap-4 rounded-panel border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="flex shrink-0 items-center gap-2.5">
          {band && <span aria-hidden="true" className={cx("size-3.5 rounded-full", DOT[band])} />}
          <span className="text-3xl font-bold text-ink">{overall === null ? "Not scored" : scoreWord(overall)}</span>
          {overall !== null && <span className="text-lg tabular-nums text-muted">{overall.toFixed(1)} / 5</span>}
        </div>
        <p className="m-0 min-w-[260px] flex-1 text-md leading-relaxed text-ink-2">
          {overall === null
            ? `Too little of this ${recording} could be checked against the transcript to give an overall score.`
            : analysis.summary}
        </p>
      </div>
      {analysis.moments && analysis.moments.items.length > 0 && onMoments && (
        <button
          type="button"
          onClick={onMoments}
          className="flex flex-wrap items-center gap-x-2 gap-y-1 self-start rounded-card border border-line bg-surface-faint px-3.5 py-2 text-left text-sm hover:border-primary"
        >
          <span className="font-semibold text-ink">What {firstName} said:</span>{" "}
          <span className="text-ink-2">{momentsSummary(analysis.moments)}.</span>{" "}
          <span className="inline-flex items-center gap-1 font-semibold text-primary">
            See each moment <Icon name="chevronRight" size={14} />
          </span>
        </button>
      )}
      <div className="grid gap-4 md:grid-cols-3">
        <Card tone="good" icon="check" label="Went well">
          {best ? <Point d={best} onWhy={onWhy} /> : <p className="m-0 text-sm text-ink-2">Nothing stood out.</p>}
        </Card>
        <Card tone="work" icon="alert" label="Needs work">
          {worst ? (
            <Point d={worst} onWhy={onWhy} />
          ) : (
            <p className="m-0 text-sm text-ink-2">Every point scored Strong.</p>
          )}
        </Card>
        <Card tone="next" icon="chevronRight" label="What happens next">
          {step ? (
            <>
              <p className="m-0 text-lg font-bold leading-snug text-ink">{step.text}</p>
              <p className="m-0 text-sm text-muted">
                {[step.who, step.when ? `“${step.when}”` : "no date said"].filter(Boolean).join(" · ")}
              </p>
              {step.ms !== null && (
                <span className="mt-auto">
                  <TimeChip ms={step.ms} onSeek={onSeek} />
                </span>
              )}
            </>
          ) : (
            <p className="m-0 text-sm text-ink-2">No next step was agreed in this {recording}.</p>
          )}
        </Card>
      </div>
      {/* One quiet line: the person's range, the evidence check and, for managers, that coaching is private. */}
      <p className="m-0 border-t border-line-subtle pt-3 text-small text-muted">
        {[history, checkedText(analysis.dimensions)].filter(Boolean).join(" ")}
        {analysis.coaching_private && (
          <span data-testid="coaching-private">
            {" "}
            {firstName}’s coaching tips are private to {firstName}.
          </span>
        )}
      </p>
    </section>
  );
}
