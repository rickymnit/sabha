// Deal card for a sales meeting: what the customer needs, the objections and how they were answered, how interested
// the customer seemed and the agreed next step. Every item is backed by a quote that was found in the transcript
// (sabha_analytics.sales); its time button plays that moment.

import { useId, type ReactNode } from "react";

import { cx } from "../../design";
import { formatClock } from "../transcript";
import { SmallPlayIcon } from "./icons";
import type { CardEvidence, DealCard, Labels } from "./types";

type ChipStyle = { text: string; tone: string };
const UNCLEAR_INTEREST: ChipStyle = { text: "Interest unclear", tone: "bg-fill text-muted" };
const UNCLEAR_SETTLED: ChipStyle = { text: "Unclear", tone: "bg-fill text-muted" };

const INTEREST: Record<string, ChipStyle> = {
  high: { text: "High interest", tone: "bg-success-tint text-success" },
  medium: { text: "Some interest", tone: "bg-warning-tint text-warning-ink" },
  low: { text: "Low interest", tone: "bg-danger-tint text-danger" },
  unclear: UNCLEAR_INTEREST,
};
const SETTLED: Record<string, ChipStyle> = {
  yes: { text: "Settled", tone: "bg-success-tint text-success" },
  no: { text: "Not settled", tone: "bg-danger-tint text-danger" },
  unclear: UNCLEAR_SETTLED,
};

function Chip({ text, tone }: { text: string; tone: string }) {
  return (
    <span className={cx("inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-small font-semibold", tone)}>
      {text}
    </span>
  );
}

function Quote({ evidence, onSeek }: { evidence: CardEvidence; onSeek: (ms: number) => void }) {
  return (
    <span className="flex items-start gap-2 text-small text-muted">
      <button
        type="button"
        onClick={() => onSeek(evidence.start_ms)}
        className="inline-flex shrink-0 items-center gap-1 rounded border border-line-input bg-surface px-1.5 py-0.5 text-primary hover:bg-primary-tint-subtle"
        aria-label={`Play from ${formatClock(evidence.start_ms)}`}
      >
        <SmallPlayIcon />
        {formatClock(evidence.start_ms)}
      </button>
      <q className="pt-0.5 italic">{evidence.quote}</q>
    </span>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <h3 className="m-0 text-sm font-semibold uppercase tracking-wide text-muted-2">{title}</h3>
      {children}
    </div>
  );
}

export interface DealCardPanelProps {
  card: DealCard;
  labels: Labels;
  onSeek: (ms: number) => void;
}

export function DealCardPanel({ card, labels, onSeek }: DealCardPanelProps) {
  const headingId = useId();
  const rep = labels.person.toLowerCase();
  const owner = { sales_rep: `The ${rep}`, customer: "The customer", both: "Both sides" } as const;
  const interest = card.interest_level ? (INTEREST[card.interest_level.value] ?? UNCLEAR_INTEREST) : null;
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-5 rounded-panel border border-line bg-surface px-6 py-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          Deal card
        </h2>
        {interest && <Chip {...interest} />}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Agreed next step">
          {card.next_step ? (
            <div className="flex flex-col gap-1.5 rounded-card border border-primary-tint-strong bg-primary-tint-subtle px-4 py-3">
              <p className="m-0 font-semibold text-ink">{card.next_step.action}</p>
              <p className="m-0 text-small text-ink-2">
                {owner[card.next_step.owner]}
                {card.next_step.due ? `, ${card.next_step.due}` : ", no date said"}
              </p>
              <Quote evidence={card.next_step.evidence} onSeek={onSeek} />
            </div>
          ) : (
            <p className="m-0 rounded-card border border-warning-border bg-warning-surface px-4 py-3 text-ink-2">
              No next step was agreed in this meeting.
            </p>
          )}
          {card.interest_level?.evidence && (
            <div className="flex flex-col gap-1">
              <p className="m-0 text-small text-muted">Interest is based on:</p>
              <Quote evidence={card.interest_level.evidence} onSeek={onSeek} />
            </div>
          )}
        </Section>

        <Section title="What the customer needs">
          {card.customer_needs.length === 0 ? (
            <p className="m-0 text-muted">The customer did not state a need in their own words.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {card.customer_needs.map((item) => (
                <li key={item.evidence.utterance_id + item.need} className="flex flex-col gap-1">
                  <span className="text-ink">{item.need}</span>
                  <Quote evidence={item.evidence} onSeek={onSeek} />
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Objections">
        {card.objections.length === 0 ? (
          <p className="m-0 text-muted">The customer raised no objections.</p>
        ) : (
          <ul className="m-0 grid list-none gap-3 p-0 lg:grid-cols-2">
            {card.objections.map((item) => (
              <li
                key={item.evidence.utterance_id + item.objection}
                className="flex flex-col gap-1.5 rounded-card border border-line-subtle px-4 py-3"
              >
                <span className="flex flex-wrap items-start justify-between gap-2">
                  <span className="font-semibold text-ink">{item.objection}</span>
                  <Chip {...(SETTLED[item.settled] ?? UNCLEAR_SETTLED)} />
                </span>
                <span className="text-small text-ink-2">
                  <span className="font-semibold">Answer:</span> {item.response}
                </span>
                <Quote evidence={item.evidence} onSeek={onSeek} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <p className="m-0 border-t border-track pt-3 text-caption text-muted">
        Every item is backed by words found in the transcript.
        {card.left_out > 0 &&
          ` ${card.left_out} ${card.left_out === 1 ? "item was" : "items were"} left out because its words could not be found.`}
      </p>
    </section>
  );
}
