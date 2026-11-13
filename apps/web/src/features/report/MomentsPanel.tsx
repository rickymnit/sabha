// "What <name> said" (owner, 2026-11-13: sales and support managers could not tell from the scores what the agent
// said well or badly). Plus points and drawbacks, each at the moment it rests on, with product statements checked
// against the organisation's approved product information. Every quote was verified against the transcript before
// it was stored (golden rule 5). The call's evaluation, so managers see it as well as the person analysed.

import { useId } from "react";

import { Icon, cx } from "../../design";
import { TimeChip } from "./SalesPanels";
import type { Moment, Moments } from "./types";

const FACT = {
  matches: { label: "Matches", tone: "bg-success-tint text-success" },
  contradicts: { label: "Contradicts", tone: "bg-danger-tint text-danger" },
} as const;

function FactCheck({ moment }: { moment: Moment }) {
  if (moment.fact === "not_covered") {
    return <span className="text-small text-muted">Not covered by your product information</span>;
  }
  if (moment.fact === null || !moment.product_info) return null;
  const { label, tone } = FACT[moment.fact];
  return (
    <details className="rounded-card bg-surface-faint px-3 py-2">
      <summary className="cursor-pointer text-small">
        <span className={cx("mr-1.5 rounded-full px-2 py-0.5 font-semibold", tone)}>{label}</span>
        <span className="font-semibold text-ink-2">{moment.product_info.title}</span>
      </summary>
      <p className="m-0 mt-1.5 whitespace-pre-line text-small text-ink-2">{moment.product_info.body}</p>
    </details>
  );
}

function Column({
  title,
  tone,
  items,
  empty,
  onSeek,
}: {
  title: string;
  tone: "good" | "bad";
  items: Moment[];
  empty: string;
  onSeek: (ms: number) => void;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col">
      <h3
        id={headingId}
        className={cx(
          "m-0 flex items-center gap-1.5 px-5 pb-1 pt-3.5 text-small font-bold uppercase tracking-wide",
          tone === "good" ? "text-success" : "text-danger",
        )}
      >
        <Icon name={tone === "good" ? "check" : "alert"} size={15} /> {title} ({items.length})
      </h3>
      {items.length === 0 ? (
        <p className="m-0 px-5 py-3 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {items.map((m) => (
            <li
              key={`${m.evidence.utterance_id}-${m.text}`}
              className="flex items-start gap-3 border-b border-line-subtle px-5 py-3 last:border-b-0"
            >
              <TimeChip ms={m.evidence.start_ms} onSeek={onSeek} />
              <span className="flex min-w-0 flex-col gap-1">
                <span className="text-ink">{m.text}</span>
                <q className="text-small italic text-muted">{m.evidence.quote}</q>
                <FactCheck moment={m} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function MomentsPanel({
  moments,
  name,
  onSeek,
}: {
  moments: Moments;
  /** The person analysed, for the heading ("What Rohit said"). */
  name: string;
  onSeek: (ms: number) => void;
}) {
  const headingId = useId();
  const plus = moments.items.filter((m) => m.kind === "plus");
  const drawbacks = moments.items.filter((m) => m.kind === "drawback");
  return (
    <section
      id="what-was-said"
      aria-labelledby={headingId}
      className="min-w-0 scroll-mt-4 rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-col gap-0.5 border-b border-line-subtle px-5 py-3.5">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          What {name} said
        </h2>
        <span className="text-small text-muted">
          Plus points and drawbacks, each at the moment it was said. Product facts are checked against your approved
          product information.
        </span>
      </div>
      <div className="grid divide-line-subtle md:grid-cols-2 md:divide-x">
        <Column title="Plus points" tone="good" items={plus} empty="None stood out." onSeek={onSeek} />
        <Column title="Drawbacks" tone="bad" items={drawbacks} empty="Nothing went wrong." onSeek={onSeek} />
      </div>
    </section>
  );
}
