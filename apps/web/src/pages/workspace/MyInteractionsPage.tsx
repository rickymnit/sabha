// /my/interactions: a sales rep's own calls and meetings (founder's Sales Executive dashboard doc, 2026-11-12),
// newest first, with whether each was a call or a meeting, the client, the AI-suggested interest and the quality
// score. Tabs: all, calls, meetings. A row opens the interaction's summary page.

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useRecordings } from "../../api/hooks";
import { formatDuration, formatWhen } from "../../app/format";
import { Button, EmptyState, Panel, PageHeader, ScoreChip, SegmentedControl, Skeleton } from "../../design";
import { InteractionChip, InterestPill } from "../../features/workspace/parts";
import { clientOf, pendingWords } from "../../features/workspace/words";
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
        description="Your calls and meetings, with what the client wants and how each one went."
        actions={<Button onClick={() => navigate("/upload")}>Add a recording</Button>}
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
            {rows.map((r) => {
              const done = r.status === "COMPLETED";
              return (
                <li key={r.id} className="border-b border-line-subtle last:border-b-0">
                  <button
                    type="button"
                    onClick={() => navigate(`/my/interactions/${r.id}`)}
                    className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 bg-transparent px-5 py-3.5 text-left hover:bg-surface-faint"
                  >
                    <InteractionChip kind={r.interaction} />
                    <span className="flex min-w-0 flex-[1_1_220px] flex-col">
                      <span className="truncate font-semibold text-ink">{clientOf(r) ?? r.title}</span>
                      <span className="text-small text-muted">
                        {formatWhen(r.recorded_at ?? r.created_at)}
                        {r.duration_ms ? ` · ${formatDuration(r.duration_ms)}` : ""}
                        {clientOf(r) ? ` · ${r.title}` : ""}
                      </span>
                    </span>
                    {done ? (
                      <span className="flex items-center gap-3">
                        <InterestPill value={r.interest_level} labels={labels} />
                        <ScoreChip score={r.overall_score} decimals={1} />
                      </span>
                    ) : (
                      <span className="text-small text-muted">{pendingWords(r.status)}</span>
                    )}
                  </button>
                </li>
              );
            })}
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
