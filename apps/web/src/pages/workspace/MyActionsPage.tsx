// /my/actions: a sales rep's own next actions (founder's Sales Executive dashboard doc, 2026-11-12): the next step
// agreed in each recent call or meeting, highest priority first, with the client and the due date. Dates are worked
// out in code from the words said; when the words name no clear date, they are shown as said.

import { useNavigate } from "react-router-dom";

import { useMyNextActions } from "../../api/hooks";
import type { NextActionItem } from "../../api/types";
import { formatWhen } from "../../app/format";
import { EmptyState, Panel, PageHeader, Skeleton, cx } from "../../design";
import { InteractionChip, InterestPill } from "../../features/workspace/parts";
import { dueText } from "../../features/workspace/words";

const GROUPS = [
  { key: "high", title: "High priority", note: "Interested clients, due within two days or overdue" },
  { key: "medium", title: "Medium priority", note: "Due this week" },
  { key: "low", title: "Low priority", note: "Later, or no date agreed" },
] as const;

const OWNER = { sales_rep: "You", customer: "The client", both: "You and the client" } as const;

export function MyActionsPage() {
  const navigate = useNavigate();
  const actions = useMyNextActions();
  const items = actions.data?.items ?? [];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="My next actions"
        description="What you agreed with each client, and when. Suggested by Sabha from your calls and meetings."
      />
      {actions.isPending ? (
        <Panel>
          <Skeleton className="h-24 w-full" />
        </Panel>
      ) : items.length === 0 ? (
        <Panel>
          <EmptyState
            title="No follow-ups waiting"
            description="When a client agrees a next step in a call or meeting, it shows here with its date."
          />
        </Panel>
      ) : (
        GROUPS.map((group) => {
          const rows = items.filter((i) => i.priority === group.key);
          if (rows.length === 0) return null;
          return (
            <Panel key={group.key} flush title={`${group.title} (${rows.length})`} description={group.note}>
              <ul className="m-0 flex list-none flex-col p-0">
                {rows.map((a) => (
                  <ActionRow
                    key={a.recording_id}
                    item={a}
                    onOpen={() => navigate(`/my/interactions/${a.recording_id}`)}
                  />
                ))}
              </ul>
            </Panel>
          );
        })
      )}
    </div>
  );
}

function ActionRow({ item, onOpen }: { item: NextActionItem; onOpen: () => void }) {
  const due = dueText(item);
  return (
    <li className="border-b border-line-subtle last:border-b-0">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full flex-wrap items-start gap-x-4 gap-y-2 bg-transparent px-5 py-3.5 text-left hover:bg-surface-faint"
      >
        <span className="flex min-w-0 flex-[1_1_280px] flex-col gap-1">
          <span className="font-semibold text-ink">{item.action}</span>
          <span className="flex flex-wrap items-center gap-2 text-small text-muted">
            <InteractionChip kind={item.interaction} />
            <span>{item.client ?? item.title}</span>
            <span>· {formatWhen(item.recorded_at)}</span>
            {item.owner && <span>· {OWNER[item.owner]}</span>}
          </span>
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          {due && (
            <span className={cx("text-sm", item.overdue ? "font-semibold text-danger" : "text-ink-2")}>{due}</span>
          )}
          <InterestPill
            value={item.interest}
            labels={item.interest && item.interest_label ? { [item.interest]: item.interest_label } : undefined}
          />
        </span>
      </button>
    </li>
  );
}
