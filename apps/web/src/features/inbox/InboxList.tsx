// What waits for a decision (GET /v1/inbox), as rows with one action each (UI v2, docs/design/v2/01-overview.png,
// "Needs your decision"). Used by the header bell and the Overview panel. Nouns come from the tenant's labels.

import type { MouseEvent } from "react";
import { useNavigate } from "react-router-dom";

import type { InboxItem, Me } from "../../api/types";
import { Icon, cx } from "../../design";
import { describeInboxItem } from "./describe";

export interface InboxListProps {
  items: readonly InboxItem[];
  me: Me;
  /** Called after an action is chosen, for example to close the bell's panel. */
  onNavigate?: () => void;
  className?: string;
}

export function InboxList({ items, me, onNavigate, className }: InboxListProps) {
  const navigate = useNavigate();
  return (
    <ul className={cx("m-0 list-none divide-y divide-line-subtle p-0", className)}>
      {items.map((item) => {
        const d = describeInboxItem(item, me.tenant.labels);
        const go = (event: MouseEvent<HTMLAnchorElement>) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
          event.preventDefault();
          onNavigate?.();
          navigate(d.to);
        };
        return (
          <li key={item.id} className="flex items-center gap-3 px-4 py-3">
            <span aria-hidden="true" className={cx("flex size-8 shrink-0 items-center justify-center rounded", d.tone)}>
              <Icon name={d.icon} size={16} />
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-sm font-semibold text-ink">{d.title}</span>
              {d.detail && <span className="truncate text-caption text-muted">{d.detail}</span>}
            </span>
            <a
              href={d.to}
              onClick={go}
              aria-label={`${d.action}: ${d.title}`}
              className="inline-flex min-h-touch shrink-0 items-center rounded border border-line-input bg-surface px-3 text-sm font-semibold text-ink no-underline hover:bg-surface-subtle"
            >
              {d.action}
            </a>
          </li>
        );
      })}
    </ul>
  );
}
