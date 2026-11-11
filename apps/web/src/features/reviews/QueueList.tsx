// Left column of the Reviews page (docs/design/v2/05-reviews.png): how many decisions are done this visit, filter
// pills with counts, and the waiting items with an icon, a heading, one line of detail and how long it has waited.

import { useId } from "react";

import { Icon, ProgressBar, cx } from "../../design";
import { waitingFor, type QueueGroup, type QueueItem } from "./queue";

export type QueueFilter = "all" | QueueGroup;

const FILTERS: { value: QueueFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "disputes", label: "Disputes" },
  { value: "speakers", label: "Speakers" },
  { value: "other", label: "Other" },
];

export interface QueueListProps {
  items: readonly QueueItem[];
  filter: QueueFilter;
  onFilter: (filter: QueueFilter) => void;
  selectedKey: string | undefined;
  onSelect: (key: string) => void;
  /** Decisions made since the page opened, for "2 of 5 decided". */
  decided: number;
  now?: Date;
}

export function QueueList({ items, filter, onFilter, selectedKey, onSelect, decided, now }: QueueListProps) {
  const listId = useId();
  const shown = filter === "all" ? items : items.filter((i) => i.group === filter);
  const total = decided + items.length;
  const count = (value: QueueFilter) =>
    value === "all" ? items.length : items.filter((i) => i.group === value).length;

  return (
    <section
      aria-label="Waiting for a decision"
      className="flex min-w-0 flex-col overflow-hidden rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-col gap-2 px-4 pb-3 pt-4">
        <div className="flex items-baseline justify-between gap-3 text-small">
          <span className="font-semibold text-ink">
            {decided} of {total} decided
          </span>
          <span className="text-muted">{items.length} left</span>
        </div>
        <ProgressBar
          value={decided}
          max={Math.max(total, 1)}
          label={`${decided} of ${total} decided`}
          valueText={`${decided} of ${total}`}
        />
      </div>
      <div role="group" aria-label="Show" className="flex flex-wrap gap-1 border-b border-line-subtle px-3 pb-3">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={filter === f.value}
            onClick={() => onFilter(f.value)}
            className="min-h-[36px] rounded-seg-outer px-3 text-sm text-ink-2 hover:bg-surface-subtle aria-pressed:bg-primary-tint aria-pressed:font-semibold aria-pressed:text-primary"
          >
            {f.label}{" "}
            <span className="tabular-nums text-muted-2 [[aria-pressed=true]_&]:text-primary">{count(f.value)}</span>
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="m-0 px-4 py-6 text-sm text-muted">Nothing waiting here.</p>
      ) : (
        <ul id={listId} aria-label="Waiting" className="m-0 flex list-none flex-col gap-1 p-2">
          {shown.map((item) => {
            const selected = item.key === selectedKey;
            return (
              <li key={item.key}>
                <button
                  type="button"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => onSelect(item.key)}
                  className={cx(
                    "flex w-full items-start gap-3 rounded-card border px-3 py-3 text-left",
                    selected
                      ? "border-primary-border bg-primary-tint-subtle"
                      : "border-transparent hover:bg-surface-faint",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-card", item.tone)}
                  >
                    <Icon name={item.icon} size={16} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="font-semibold text-ink">{item.title}</span>
                      <span className="shrink-0 text-small text-muted">{waitingFor(item.at, now)}</span>
                    </span>
                    <span className="line-clamp-2 text-sm text-ink-2">{item.detail}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
