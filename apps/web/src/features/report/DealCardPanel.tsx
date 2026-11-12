// "The deal at a glance" for a sales conversation (UI v2 sales report, docs/design/v2 PDF pages 5 and 9): four tiles
// (interest, what they need, the next step, the open issue) and, behind "Show evidence", every deal card item with
// the quote it rests on: what they need, what they use today, the objections and how they were answered. Every item
// is backed by a quote that was found in the transcript (sabha_analytics.sales); its time button plays that moment.

import { useId, useState, type ReactNode } from "react";

import { Button, cx } from "../../design";
import { formatClock } from "../transcript";
import { SmallGoIcon, SmallPauseIcon, SmallPlayIcon } from "./icons";
import { usePlayingFrom, useSeekMode } from "./seekMode";
import { interestView, type Tone } from "./interest";
import type { CardEvidence, DealCard, Labels } from "./types";

const SETTLED: Record<string, { text: string; tone: string }> = {
  yes: { text: "Handled", tone: "bg-success-tint text-success" },
  no: { text: "Open", tone: "bg-danger-tint text-danger" },
  unclear: { text: "Unclear", tone: "bg-fill text-muted" },
};
const DOT: Record<Tone, string> = {
  neutral: "bg-muted-2",
  good: "bg-success-bar",
  warn: "bg-warning-bar",
  bad: "bg-danger-bar",
};
const TILE: Record<Tone, string> = {
  neutral: "bg-surface",
  good: "bg-surface",
  warn: "bg-warning-surface",
  bad: "bg-danger-tint/40",
};

export function Quote({ evidence, onSeek }: { evidence: CardEvidence; onSeek: (ms: number) => void }) {
  const go = useSeekMode() === "go";
  const pausable = usePlayingFrom() === evidence.start_ms;
  const time = formatClock(evidence.start_ms);
  return (
    <span className="flex items-start gap-2.5 rounded-card border border-warning-border bg-warning-surface px-3 py-2 text-small text-ink-2">
      <button
        type="button"
        onClick={() => onSeek(evidence.start_ms)}
        className="inline-flex shrink-0 items-center gap-1 rounded border border-line-input bg-surface px-1.5 py-0.5 font-semibold tabular-nums text-warning-ink hover:bg-warning-tint-subtle"
        aria-label={
          go ? `Go to ${time} in the transcript` : pausable ? `Pause, playing from ${time}` : `Play from ${time}`
        }
      >
        {go ? <SmallGoIcon /> : pausable ? <SmallPauseIcon /> : <SmallPlayIcon />}
        {go ? `Go to ${time}` : time}
      </button>
      <q className="pt-0.5">{evidence.quote}</q>
    </span>
  );
}

function Tile({ label, tone, title, detail }: { label: string; tone: Tone; title: string; detail?: ReactNode }) {
  return (
    <div className="min-w-0 bg-surface">
      <div className={cx("flex h-full min-w-0 flex-col gap-1 px-5 py-4", TILE[tone])}>
        <span className="flex items-center gap-1.5 text-small text-muted">
          <span aria-hidden="true" className={cx("h-2 w-2 rounded-full", DOT[tone])} />
          {label}
        </span>
        <span className="text-lg font-semibold leading-snug text-ink">{title}</span>
        {detail && <span className="text-small text-ink-2">{detail}</span>}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <h3 className="m-0 text-sm font-semibold text-muted">{title}</h3>
      {children}
    </div>
  );
}

export interface DealCardPanelProps {
  card: DealCard;
  labels: Labels;
  onSeek: (ms: number) => void;
  /** Start with the evidence open (the person's own view, tests). */
  defaultOpen?: boolean;
  /** The rubric's words for the interest levels (output_labels.interest_level). */
  interestLabels?: Record<string, string>;
}

export function DealCardPanel({ card, labels, onSeek, defaultOpen = false, interestLabels }: DealCardPanelProps) {
  const headingId = useId();
  const evidenceId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const rep = labels.person.toLowerCase();
  const owner = { sales_rep: `The ${rep}`, customer: "The customer", both: "Both sides" } as const;
  const interest = card.interest_level ? interestView(card.interest_level.value, interestLabels) : null;
  const [need, ...moreNeeds] = card.customer_needs;
  const openIssue = card.objections.find((o) => o.settled !== "yes");
  const next = card.next_step;

  return (
    <section
      aria-labelledby={headingId}
      className="min-w-0 overflow-hidden rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-subtle px-5 py-3.5">
        <div className="flex flex-col gap-0.5">
          <h2 id={headingId} className="m-0 text-lg font-semibold">
            The deal at a glance
          </h2>
          <span className="text-small text-muted">
            {card.client_name ? `${card.client_name.name} · ` : ""}Every line is backed by something the customer said
          </span>
        </div>
        <Button variant="secondary" aria-expanded={open} aria-controls={evidenceId} onClick={() => setOpen((o) => !o)}>
          {open ? "Hide evidence" : "Show evidence"}
        </Button>
      </div>

      <div className="grid gap-px bg-line-subtle sm:grid-cols-2 xl:grid-cols-4">
        <Tile
          label="Interest"
          tone={interest?.tone ?? "neutral"}
          title={interest?.text ?? "Unclear"}
          detail={card.interest_level?.evidence ? `“${card.interest_level.evidence.quote}”` : undefined}
        />
        <Tile
          label="What they need"
          tone="neutral"
          title={need?.need ?? "No need stated"}
          detail={
            moreNeeds.length > 0
              ? `and ${moreNeeds.length} more`
              : need
                ? undefined
                : "The customer did not say it in their own words"
          }
        />
        <Tile
          label="Next step"
          tone={next ? (next.due ? "good" : "warn") : "bad"}
          title={next?.action ?? "No next step agreed"}
          detail={
            next ? (
              <span className={next.due ? undefined : "font-semibold text-warning-ink"}>
                {next.due ? `${owner[next.owner]}, ${next.due}` : "No date agreed"}
              </span>
            ) : undefined
          }
        />
        <Tile
          label="Open issue"
          tone={openIssue ? "bad" : "neutral"}
          title={openIssue?.objection ?? "None left open"}
          detail={
            openIssue ? (
              <span className="font-semibold text-danger">
                {openIssue.settled === "no" ? "Not answered on the call" : "Unclear whether it was settled"}
              </span>
            ) : card.objections.length > 0 ? (
              `${card.objections.length} ${card.objections.length === 1 ? "objection" : "objections"} handled`
            ) : (
              "No objections raised"
            )
          }
        />
      </div>

      {open && (
        <div id={evidenceId} className="flex flex-col gap-6 border-t border-line-subtle px-5 py-5">
          <div className="grid gap-6 lg:grid-cols-2">
            <Section title="What they need">
              {card.customer_needs.length === 0 ? (
                <p className="m-0 text-muted">The customer did not state a need in their own words.</p>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-3 p-0">
                  {card.customer_needs.map((item) => (
                    <li key={item.evidence.utterance_id + item.need} className="flex flex-col gap-1.5">
                      <span className="text-ink">{item.need}</span>
                      <Quote evidence={item.evidence} onSeek={onSeek} />
                    </li>
                  ))}
                </ul>
              )}
            </Section>
            {card.current_setup && card.current_setup.length > 0 && (
              <Section title="What they use today">
                <ul className="m-0 flex list-none flex-col gap-3 p-0">
                  {card.current_setup.map((item) => (
                    <li key={item.evidence.utterance_id + item.fact} className="flex flex-col gap-1.5">
                      <span className="text-ink">{item.fact}</span>
                      <Quote evidence={item.evidence} onSeek={onSeek} />
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            <Section title="Next step">
              {next ? (
                <div className="flex flex-col gap-1.5">
                  <span className="text-ink">{next.action}</span>
                  <span className="text-small text-ink-2">
                    {owner[next.owner]}
                    {next.due ? `, ${next.due}` : ", no date said"}
                  </span>
                  <Quote evidence={next.evidence} onSeek={onSeek} />
                </div>
              ) : (
                <p className="m-0 text-muted">No next step was agreed in this meeting.</p>
              )}
            </Section>
            {card.interest_level?.evidence && (
              <Section title="Interest is based on">
                <Quote evidence={card.interest_level.evidence} onSeek={onSeek} />
              </Section>
            )}
          </div>

          <Section title="Objections raised">
            {card.objections.length === 0 ? (
              <p className="m-0 text-muted">The customer raised no objections.</p>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {card.objections.map((item) => {
                  const settled = SETTLED[item.settled] ?? SETTLED.unclear;
                  return (
                    <li
                      key={item.evidence.utterance_id + item.objection}
                      className="flex flex-col gap-2 rounded-card bg-surface-subtle px-4 py-3"
                    >
                      <span className="flex flex-wrap items-center gap-2.5">
                        <span className={cx("rounded-full px-2.5 py-0.5 text-small font-semibold", settled?.tone)}>
                          {settled?.text}
                        </span>
                        <span className="font-semibold text-ink">{item.objection}</span>
                      </span>
                      <span className="text-small text-ink-2">
                        <span className="font-semibold">Answer:</span> {item.response}
                      </span>
                      <Quote evidence={item.evidence} onSeek={onSeek} />
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>

          <p className="m-0 border-t border-track pt-3 text-caption text-muted">
            Every item is backed by words found in the transcript.
            {card.left_out > 0 &&
              ` ${card.left_out} ${card.left_out === 1 ? "item was" : "items were"} left out because its words could not be found.`}
          </p>
        </div>
      )}
    </section>
  );
}
