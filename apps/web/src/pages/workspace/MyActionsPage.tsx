// /my/actions: a sales rep's own next actions (founder's Sales Executive dashboard doc, 2026-11-12): the next step
// agreed in each recent call or meeting, highest priority first, with the client and the due date. Dates are worked
// out in code from the words said; when the words name no clear date, they are shown as said.

import { useNavigate } from "react-router-dom";

import { useMyNextActions } from "../../api/hooks";
import { EmptyState, Panel, PageHeader, Skeleton } from "../../design";
import { ActionRow } from "../../features/workspace/ActionRow";

const GROUPS = [
  { key: "high", title: "Do first", note: "Interested clients, due in the next two days or overdue" },
  { key: "medium", title: "This week", note: "Due in the next seven days" },
  { key: "low", title: "Later", note: "Due later, or no date agreed" },
] as const;

export function MyActionsPage() {
  const navigate = useNavigate();
  const actions = useMyNextActions();
  const items = actions.data?.items ?? [];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="My next actions"
        description="What you agreed with each client, and when. Sabha picks these up from your calls and meetings."
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
            <Panel key={group.key} flush title={`${group.title} · ${rows.length}`} description={group.note}>
              <ul className="m-0 flex list-none flex-col p-0">
                {rows.map((a) => (
                  <ActionRow
                    key={a.recording_id}
                    item={a}
                    showPriority={false}
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
