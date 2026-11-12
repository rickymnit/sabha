// /my/interactions: a sales rep's own calls and meetings (founder's Sales Executive dashboard doc, 2026-11-12),
// newest first, by client name (ConversationRow), with the AI-suggested interest and the score in words. Tabs: all, calls, meetings. A row opens the interaction's summary page.

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useRecordings } from "../../api/hooks";
import { Button, EmptyState, Panel, PageHeader, SegmentedControl, Skeleton } from "../../design";
import { ConversationRow } from "../../features/workspace/ConversationRow";
import { useInterestLabels } from "../../features/workspace/useInterestLabels";

type Tab = "all" | "call" | "meeting";

export function MyInteractionsPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("all");
  const list = useRecordings({ type: "sales", interaction: tab === "all" ? null : tab }, 20);
  const labels = useInterestLabels();
  const rows = list.data?.pages.flatMap((p) => p.items) ?? [];
  const none = tab === "call" ? "calls" : tab === "meeting" ? "meetings" : "calls or meetings";
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="My interactions"
        description="Every call and meeting, newest first. Open one to see what the client wants and what to do next."
      />
      <Panel
        flush
        title="Calls and meetings"
        actions={
          <SegmentedControl
            label="Show"
            value={tab}
            onChange={setTab}
            options={[
              { value: "all", label: "All" },
              { value: "call", label: "Calls" },
              { value: "meeting", label: "Meetings" },
            ]}
          />
        }
      >
        {list.isPending ? (
          <div className="flex flex-col gap-2 p-5">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : list.isError ? (
          <EmptyState
            headingAs="h3"
            title="We couldn't load your interactions"
            description="Please try again in a moment."
          />
        ) : rows.length === 0 ? (
          <EmptyState
            headingAs="h3"
            title={`No ${none} yet`}
            action={<Button onClick={() => navigate("/upload")}>Add a recording</Button>}
          />
        ) : (
          <ul className="m-0 flex list-none flex-col p-0">
            {rows.map((r) => (
              <ConversationRow key={r.id} row={r} labels={labels} onOpen={() => navigate(`/my/interactions/${r.id}`)} />
            ))}
          </ul>
        )}
        {list.hasNextPage && (
          <div className="border-t border-line-subtle px-5 py-3">
            <Button variant="secondary" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
              {list.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          </div>
        )}
      </Panel>
    </div>
  );
}
