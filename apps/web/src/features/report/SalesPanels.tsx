// Sales report panels (UI v2, docs/design/v2 PDF pages 5 and 9): the overall card with the five-level scale, what
// went well and what to fix first; the agreed next step in a dark card; and "Talk and listen", the talk shares and
// counts computed in code from the transcript (golden rule 5: numbers come from code, never the AI).

import { useId } from "react";

import { cx, scoreBand } from "../../design";
import { formatClock } from "../transcript";
import { checkedText, formatMetricValue, formatScore } from "./format";
import { CheckIcon, SmallGoIcon, SmallPauseIcon } from "./icons";
import { usePlayingFrom, useSeekMode } from "./seekMode";
import type { AnalysisReport, DealCard, Labels, Metric, ReportRecording } from "./types";

const LEVELS = ["Weak", "Needs work", "OK", "Good", "Strong"] as const;
const SOLID = { low: "bg-danger-bar", mid: "bg-warning-bar", good: "bg-success-bar" } as const;
const SOFT = { low: "bg-danger-tint", mid: "bg-warning-tint", good: "bg-success-tint" } as const;
const CHIP = {
  low: "bg-danger-tint text-danger",
  mid: "bg-warning-tint text-warning-ink",
  good: "bg-success-tint text-success",
} as const;

function TimeChip({ ms, onSeek }: { ms: number; onSeek: (ms: number) => void }) {
  const go = useSeekMode() === "go";
  const pausable = usePlayingFrom() === ms;
  const time = formatClock(ms);
  return (
    <button
      type="button"
      onClick={() => onSeek(ms)}
      aria-label={
        go ? `Go to ${time} in the transcript` : pausable ? `Pause, playing from ${time}` : `Play from ${time}`
      }
      className="inline-flex min-w-[54px] shrink-0 items-center justify-center gap-1 rounded-md border border-primary-border bg-primary-tint-subtle px-2 py-1 text-small font-semibold tabular-nums text-primary-hover hover:bg-primary-tint"
    >
      {go ? <SmallGoIcon /> : pausable ? <SmallPauseIcon /> : null}
      {time}
    </button>
  );
}

/** "Lowest of Rohit's last 11 calls (range 2.1 to 3.9)": this score among the person's earlier ones. */
function historyText(overall: number, history: AnalysisReport["person_history"], name: string, plural: string) {
  if (!history || history.count === 0) return null;
  const count = history.count + 1;
  const min = Math.min(history.min, overall);
  const max = Math.max(history.max, overall);
  const range = `range ${formatScore(min)} to ${formatScore(max)}`;
  if (overall <= history.min) return `Lowest of ${name}’s last ${count} ${plural} (${range}).`;
  if (overall >= history.max) return `Highest of ${name}’s last ${count} ${plural} (${range}).`;
  return `${name}’s last ${count} ${plural}: ${range}.`;
}

export function SalesOverall({
  analysis,
  recording,
  labels,
  onSeek,
}: {
  analysis: AnalysisReport;
  recording: ReportRecording;
  labels: Labels;
  onSeek: (ms: number) => void;
}) {
  const headingId = useId();
  const { overall } = analysis;
  const band = overall === null ? "mid" : scoreBand(overall);
  const level = overall === null ? 0 : Math.min(5, Math.max(1, Math.round(overall)));
  const firstName = recording.person.name.split(" ")[0] ?? recording.person.name;
  const past =
    overall === null
      ? null
      : historyText(overall, analysis.person_history, firstName, labels.recording_plural.toLowerCase());
  const [headline, ...rest] = analysis.summary.split(/(?<=\.)\s+/);

  return (
    <section aria-labelledby={headingId} className="overflow-hidden rounded-panel border border-line bg-surface">
      <div className="flex flex-wrap">
        <div className="flex flex-[1_1_270px] flex-col gap-2 border-b border-line-subtle px-6 py-5 sm:border-b-0 sm:border-r">
          <span className="text-sm text-muted">Overall</span>
          {overall === null ? (
            <>
              <span className="text-hero font-semibold text-muted-2">
                <span aria-hidden="true">—</span>
                <span className="sr-only">No overall score</span>
              </span>
              <span className="text-small text-muted">
                Too few rubric points could be checked for an overall score.
              </span>
            </>
          ) : (
            <>
              <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-hero font-semibold" data-testid="overall-score">
                  {formatScore(overall)}
                  <span className="text-xl font-medium tracking-normal text-muted-2"> of 5</span>
                </span>
                <span className={cx("rounded-full px-2.5 py-0.5 text-sm font-semibold", CHIP[band])}>
                  {LEVELS[level - 1]}
                </span>
              </span>
              <ol aria-label="Where this sits" className="m-0 grid list-none grid-cols-5 gap-1.5 p-0">
                {LEVELS.map((name, i) => (
                  <li key={name} className="flex flex-col gap-1" aria-current={i + 1 === level ? "true" : undefined}>
                    <span
                      aria-hidden="true"
                      className={cx(
                        "h-1.5 rounded-full",
                        i + 1 === level ? SOLID[band] : i + 1 < level ? SOFT[band] : "bg-track",
                      )}
                    />
                    <span
                      className={cx(
                        "text-2xs leading-tight [overflow-wrap:anywhere]",
                        i + 1 === level ? cx("font-semibold", CHIP[band].split(" ")[1]) : "text-muted",
                      )}
                    >
                      {name}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          )}
          {past && (
            <span data-testid="overall-history" className="text-small text-ink-2">
              {past}
            </span>
          )}
        </div>
        <div className="flex min-w-0 flex-[999_1_380px] flex-col gap-4 px-6 py-5">
          <h2 id={headingId} className="m-0 text-lg font-semibold leading-snug">
            {headline}
          </h2>
          {rest.length > 0 && <p className="m-0 -mt-2 text-ink-2">{rest.join(" ")}</p>}
          <div className="grid gap-5 md:grid-cols-2">
            {analysis.strengths.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="flex items-center gap-1.5 text-sm font-semibold text-success">
                  <span className="grid h-4.5 w-4.5 place-items-center rounded-full bg-success-tint">
                    <CheckIcon />
                  </span>
                  Went well
                </span>
                <ul className="m-0 flex list-none flex-col gap-2 p-0 text-ink-2">
                  {analysis.strengths.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {analysis.suggestions.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="flex items-center gap-1.5 text-sm font-semibold text-danger">
                  <span
                    aria-hidden="true"
                    className="grid h-4.5 w-4.5 place-items-center rounded-full bg-danger-tint text-2xs font-bold"
                  >
                    !
                  </span>
                  Fix first
                </span>
                <ul
                  aria-label={`What to fix in the next ${labels.recording.toLowerCase()}`}
                  className="m-0 flex list-none flex-col gap-2 p-0"
                >
                  {analysis.suggestions.map((s, i) => (
                    <li key={`${s.utterance_id}-${i}`} className="flex items-start gap-2.5 text-ink-2">
                      <TimeChip ms={s.start_ms} onSeek={onSeek} />
                      <span className="pt-0.5">{s.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
      <p className="m-0 flex items-center gap-2 border-t border-line-subtle bg-surface-faint px-6 py-2.5 text-small text-ink-2">
        <span aria-hidden="true" className="text-success">
          <CheckIcon />
        </span>
        <span data-testid="overall-checked">{checkedText(analysis.dimensions)}</span>
      </p>
    </section>
  );
}

export function NextStepCard({
  step,
  repName,
  onSeek,
}: {
  step: DealCard["next_step"];
  /** The rep's first name, for "Owner: Rohit". */
  repName: string;
  onSeek: (ms: number) => void;
}) {
  const headingId = useId();
  const owner = { sales_rep: repName, customer: "Customer", both: `${repName} and the customer` };
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3 rounded-panel bg-ink px-5 py-5 text-surface">
      <h2 id={headingId} className="m-0 text-sm font-semibold text-primary-tint-strong">
        Next step agreed
      </h2>
      {step ? (
        <>
          <p className="m-0 text-xl font-semibold leading-snug">{step.action}</p>
          <div className="flex flex-wrap gap-2 text-small">
            <span className="rounded-full bg-surface/10 px-3 py-1">
              {step.due ? `Due ${step.due}` : "No date agreed"}
            </span>
            <span className="rounded-full bg-surface/10 px-3 py-1">Owner: {owner[step.owner]}</span>
            <button
              type="button"
              onClick={() => onSeek(step.evidence.start_ms)}
              className="rounded-full bg-surface/10 px-3 py-1 text-surface hover:bg-surface/20"
            >
              Said at {formatClock(step.evidence.start_ms)}
            </button>
          </div>
        </>
      ) : (
        <p className="m-0 text-lg font-semibold">No next step was agreed.</p>
      )}
    </section>
  );
}

/** Talk shares and counts from the computed metrics; rows without a measured value are left out. */
export function TalkListenCard({
  metrics,
  labels,
  repName,
  onSeek,
}: {
  metrics: readonly Metric[];
  labels: Labels;
  repName: string;
  onSeek: (ms: number) => void;
}) {
  const headingId = useId();
  const byKey = new Map(metrics.map((m) => [m.key, m]));
  const rep = byKey.get("sales_rep_talk_share")?.value ?? null;
  const customer = byKey.get("customer_talk_share")?.value ?? null;
  const questions = byKey.get("sales_rep_question_count");
  const open = byKey.get("open_question_ratio");
  const monologue = byKey.get("longest_monologue_s");
  const rows: { label: string; value: string; action?: () => void }[] = [];
  if (questions?.value != null) rows.push({ label: `Questions ${repName} asked`, value: String(questions.value) });
  if (open?.value != null) rows.push({ label: "Open questions", value: formatMetricValue(open) ?? "" });
  if (monologue?.value != null) {
    const range = monologue.range;
    rows.push({
      label: "Longest monologue",
      value: formatMetricValue(monologue) ?? "",
      action: range ? () => onSeek(range.start_ms) : undefined,
    });
  }
  if (rep === null && customer === null && rows.length === 0) return null;
  const total = (rep ?? 0) + (customer ?? 0) || 1;
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-3.5 rounded-panel border border-line bg-surface px-5 py-5"
    >
      <h2 id={headingId} className="m-0 text-lg font-semibold">
        Talk and listen
      </h2>
      {rep !== null && customer !== null && (
        <div className="flex flex-col gap-1.5">
          <div aria-hidden="true" className="flex h-2.5 overflow-hidden rounded-full">
            <span className="bg-speaker-staff" style={{ width: `${(rep / total) * 100}%` }} />
            <span className="bg-speaker-other" style={{ width: `${(customer / total) * 100}%` }} />
          </div>
          <div className="flex justify-between text-sm font-semibold">
            <span className="text-primary">
              {repName} {Math.round(rep * 100)}%
            </span>
            <span className="text-warning-ink">Customer {Math.round(customer * 100)}%</span>
          </div>
        </div>
      )}
      {rows.length > 0 && (
        <dl className="m-0 flex flex-col gap-2">
          {rows.map((r) => (
            <div key={r.label} className="flex items-baseline justify-between gap-3 text-sm">
              <dt className="text-ink-2">{r.label}</dt>
              <dd className="m-0 font-semibold tabular-nums text-ink">
                {r.action ? (
                  <button type="button" onClick={r.action} className="font-semibold text-primary hover:underline">
                    {r.value}
                  </button>
                ) : (
                  r.value
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className="m-0 text-small text-muted">
        Counted by software from the transcript, not judged by AI. Only the {labels.person.toLowerCase()} is scored.
      </p>
    </section>
  );
}
