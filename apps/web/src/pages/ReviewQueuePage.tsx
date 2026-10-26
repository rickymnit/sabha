// /reviews (ADR 0007, P6.7): for owners, admins, managers and reviewers, two tabs. "Needs review": recordings Sabha
// stopped on because it should not guess; each row says why in plain words and opens the review. "Disputes": scores
// someone asked a reviewer to look at again (DisputeQueue). The tab is kept in the address (?tab=disputes).

import type { MouseEvent } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import { useDisputes, useReviews } from "../api/hooks";
import type { Me, RecordingItem } from "../api/types";
import { capitalise, formatWhen } from "../app/format";
import {
  Button,
  EmptyState,
  Icon,
  PageHeader,
  Panel,
  SegmentedControl,
  Skeleton,
  SkeletonGroup,
  Table,
} from "../design";
import { DisputeQueue } from "./DisputeQueue";

type Tab = "review" | "disputes";

export function ReviewQueuePage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "disputes" ? "disputes" : "review";
  const reviews = useReviews();
  const disputes = useDisputes();
  const rows = reviews.data?.items ?? [];
  const query = tab === "disputes" ? disputes : reviews;
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  const open = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(`/reviews/${id}`);
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reviews"
        description={`${capitalise(labels.recording_plural)} Sabha paused on rather than guess, and scores someone asked to have looked at again.`}
      />
      <SegmentedControl
        label="Show"
        value={tab}
        onChange={(value) => setParams(value === "disputes" ? { tab: "disputes" } : {}, { replace: true })}
        options={[
          { value: "review", label: `Needs review${reviews.data ? ` (${rows.length})` : ""}` },
          { value: "disputes", label: `Disputes${disputes.data ? ` (${disputes.data.items.length})` : ""}` },
        ]}
      />
      {query.isError ? (
        <Panel>
          <EmptyState
            icon={<Icon name="alert" size={26} />}
            title="We couldn't load the reviews"
            description="Please try again in a moment."
            action={<Button onClick={() => void query.refetch()}>Try again</Button>}
          />
        </Panel>
      ) : query.isPending ? (
        <Panel>
          <SkeletonGroup label="Loading reviews" className="flex flex-col gap-3">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-4 w-1/3" />
          </SkeletonGroup>
        </Panel>
      ) : tab === "disputes" && disputes.data ? (
        <DisputeQueue page={disputes.data} personWord={labels.person} />
      ) : rows.length === 0 ? (
        <Panel>
          <EmptyState
            className="py-14"
            icon={<Icon name="reviews" size={26} />}
            title="Nothing waiting for review"
            description={`When Sabha is unsure about a ${labels.recording.toLowerCase()}, for example who the ${labels.person.toLowerCase()} is, it appears here.`}
          />
        </Panel>
      ) : (
        <Panel flush aria-label="Waiting for review" footer={<span>{rows.length} waiting</span>}>
          <Table<RecordingItem>
            aria-label="Waiting for review"
            rows={rows}
            rowKey={(r) => r.id}
            minWidth={0}
            rowClassName="relative hover:bg-surface-faint"
            columns={[
              {
                key: "title",
                header: capitalise(labels.recording),
                render: (r) => (
                  <div className="flex flex-col gap-0.5">
                    <a
                      href={`/reviews/${r.id}`}
                      onClick={(e) => open(e, r.id)}
                      className="font-semibold text-ink no-underline after:absolute after:inset-0 hover:text-primary-hover"
                    >
                      {r.title}
                    </a>
                    <span className="text-small text-muted">
                      {[r.person?.name, r.unit_id ? units.get(r.unit_id) : undefined].filter(Boolean).join(", ")}
                    </span>
                  </div>
                ),
              },
              {
                key: "why",
                header: "Why",
                render: (r) => <span className="text-ink-2">{r.status_note}</span>,
              },
              {
                key: "since",
                header: "Waiting since",
                align: "right",
                hideOnPhone: true,
                className: "whitespace-nowrap",
                render: (r) => formatWhen(r.status_changed_at ?? r.created_at),
              },
              {
                key: "go",
                header: "Action",
                hideHeader: true,
                align: "right",
                hideOnPhone: true,
                render: () => (
                  <span className="inline-flex items-center gap-1 font-semibold text-primary">
                    Review <Icon name="chevronRight" size={16} />
                  </span>
                ),
              },
            ]}
          />
        </Panel>
      )}
    </div>
  );
}
