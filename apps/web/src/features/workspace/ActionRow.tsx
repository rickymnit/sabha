// One next action (Overview, My next actions): what to do as an instruction, when, and for which client. A tag only
// when it should be done soon ("Do first", "This week").

import type { NextActionItem } from "../../api/types";
import { cx } from "../../design";
import { PriorityPill } from "./parts";
import { conversationName, dueText, plainAction } from "./words";

const OWNER = { sales_rep: null, customer: "Waiting on the client", both: "You and the client" } as const;

export function ActionRow({
  item,
  onOpen,
  showPriority = true,
}: {
  item: NextActionItem;
  onOpen: () => void;
  /** Off where the list is already grouped by priority. */
  showPriority?: boolean;
}) {
  const due = dueText(item);
  const owner = item.owner ? OWNER[item.owner] : null;
  return (
    <li className="border-b border-line-subtle last:border-b-0">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full flex-col gap-1 bg-transparent px-5 py-3.5 text-left hover:bg-surface-faint"
      >
        {((showPriority && item.priority !== "low") || due) && (
          <span className="flex flex-wrap items-center gap-2">
            {showPriority && <PriorityPill priority={item.priority} />}
            {due && (
              <span className={cx("text-small", item.overdue ? "font-semibold text-danger" : "text-ink-2")}>{due}</span>
            )}
          </span>
        )}
        <span className="font-semibold text-ink">{plainAction(item.action)}</span>
        <span className="text-small text-muted">
          {conversationName(item.client, item.interaction, item.recorded_at)}
          {owner ? ` · ${owner}` : ""}
        </span>
      </button>
    </li>
  );
}
