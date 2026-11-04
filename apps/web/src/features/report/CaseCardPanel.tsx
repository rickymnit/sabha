// Case card for a support call: the product, the customer's problem, the steps tried, how the call ended and any
// promised follow-up. Every item is backed by a quote that was found in the transcript (sabha_analytics.support); its
// time button plays that moment. Outcomes come from the tenant's rubric, so unknown values are shown as plain words.

import { useId, type ReactNode } from "react";

import { cx } from "../../design";
import { Quote } from "./DealCardPanel";
import { words } from "./format";
import type { CaseCard } from "./types";

type ChipStyle = { text: string; tone: string };
const UNCLEAR_OUTCOME: ChipStyle = { text: "Outcome unclear", tone: "bg-fill text-muted" };

const OUTCOME: Record<string, ChipStyle> = {
  solved: { text: "Solved", tone: "bg-success-tint text-success" },
  follow_up: { text: "Follow-up promised", tone: "bg-warning-tint text-warning-ink" },
  escalated: { text: "Escalated", tone: "bg-warning-tint text-warning-ink" },
  not_solved: { text: "Not solved", tone: "bg-danger-tint text-danger" },
  unclear: UNCLEAR_OUTCOME,
};

function Chip({ text, tone }: ChipStyle) {
  return (
    <span className={cx("inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-small font-semibold", tone)}>
      {text}
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

export interface CaseCardPanelProps {
  card: CaseCard;
  onSeek: (ms: number) => void;
}

export function CaseCardPanel({ card, onSeek }: CaseCardPanelProps) {
  const headingId = useId();
  const outcome = card.outcome
    ? (OUTCOME[card.outcome.value] ?? { text: words(card.outcome.value), tone: "bg-fill text-muted" })
    : null;
  const owner = { support_agent: "The agent", customer: "The customer", both: "Both sides" } as const;
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-5 rounded-panel border border-line bg-surface px-6 py-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          Case card
        </h2>
        <span className="flex flex-wrap items-center gap-2">
          {card.product && <Chip text={card.product.name} tone="bg-primary-tint-subtle text-primary" />}
          {outcome && <Chip {...outcome} />}
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="The problem">
          {card.problem ? (
            <div className="flex flex-col gap-1">
              <span className="text-ink">{card.problem.problem}</span>
              <Quote evidence={card.problem.evidence} onSeek={onSeek} />
            </div>
          ) : (
            <p className="m-0 text-muted">The customer did not describe a problem.</p>
          )}
          {card.product && (
            <div className="flex flex-col gap-1">
              <p className="m-0 text-small text-muted">The product is named here:</p>
              <Quote evidence={card.product.evidence} onSeek={onSeek} />
            </div>
          )}
        </Section>

        <Section title="How it ended">
          {card.outcome?.evidence && <Quote evidence={card.outcome.evidence} onSeek={onSeek} />}
          {card.follow_up ? (
            <div className="flex flex-col gap-1.5 rounded-card border border-primary-tint-strong bg-primary-tint-subtle px-4 py-3">
              <p className="m-0 font-semibold text-ink">{card.follow_up.action}</p>
              <p className="m-0 text-small text-ink-2">
                {owner[card.follow_up.owner]}
                {card.follow_up.due ? `, ${card.follow_up.due}` : ", no date said"}
              </p>
              <Quote evidence={card.follow_up.evidence} onSeek={onSeek} />
            </div>
          ) : (
            <p className="m-0 text-muted">No follow-up was promised on this call.</p>
          )}
        </Section>
      </div>

      <Section title="Steps tried">
        {card.steps_tried.length === 0 ? (
          <p className="m-0 text-muted">No steps to fix the problem were tried on this call.</p>
        ) : (
          <ol className="m-0 flex list-none flex-col gap-3 p-0">
            {card.steps_tried.map((item, index) => (
              <li key={item.evidence.utterance_id + item.step} className="flex items-start gap-3">
                <span
                  aria-hidden="true"
                  className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-fill text-small font-semibold text-ink-2"
                >
                  {index + 1}
                </span>
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="text-ink">
                    {item.step}{" "}
                    <span className="text-small text-muted">
                      ({item.by === "customer" ? "by the customer" : "with the agent"})
                    </span>
                  </span>
                  <Quote evidence={item.evidence} onSeek={onSeek} />
                </span>
              </li>
            ))}
          </ol>
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
