// Front-desk ticket for a reception call or walk-in visit: what the person needed, the category, how it ended and any
// follow-up. Both quotes were found in the transcript (sabha_analytics.reception); their time buttons play that moment.
// Categories and statuses come from the tenant's rubric, so unknown values are shown as plain words, never dropped.

import { useId, type ReactNode } from "react";

import { cx } from "../../design";
import { Quote } from "./DealCardPanel";
import { words } from "./format";
import type { Ticket } from "./types";

type ChipStyle = { text: string; tone: string };

const STATUS: Record<string, ChipStyle> = {
  resolved: { text: "Resolved", tone: "bg-success-tint text-success" },
  follow_up_needed: { text: "Follow-up needed", tone: "bg-warning-tint text-warning-ink" },
  escalated: { text: "Escalated", tone: "bg-danger-tint text-danger" },
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

export interface TicketPanelProps {
  ticket: Ticket;
  onSeek: (ms: number) => void;
}

export function TicketPanel({ ticket, onSeek }: TicketPanelProps) {
  const headingId = useId();
  const status = STATUS[ticket.status] ?? { text: words(ticket.status), tone: "bg-fill text-muted" };
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-5 rounded-panel border border-line bg-surface px-6 py-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          Front desk ticket
        </h2>
        <span className="flex flex-wrap items-center gap-2">
          <Chip text={words(ticket.category)} tone="bg-primary-tint-subtle text-primary" />
          <Chip {...status} />
        </span>
      </div>

      <p className="m-0 text-ink">{ticket.summary}</p>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="What they needed">
          <Quote evidence={ticket.evidence.need} onSeek={onSeek} />
        </Section>
        <Section title="How it ended">
          <Quote evidence={ticket.evidence.outcome} onSeek={onSeek} />
          {ticket.follow_up && (
            <div className="flex flex-col gap-1 rounded-card border border-warning-border bg-warning-surface px-4 py-3">
              <p className="m-0 font-semibold text-ink">{ticket.follow_up.text}</p>
              <p className="m-0 text-small text-ink-2">Owner: {ticket.follow_up.owner_role}</p>
            </div>
          )}
        </Section>
      </div>

      <p className="m-0 border-t border-track pt-3 text-caption text-muted">
        Both quotes are words found in the transcript.
      </p>
    </section>
  );
}
