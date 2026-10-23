// /reviews (ADR 0007): recordings Sabha stopped on because it should not guess, for owners, admins, managers and
// reviewers. Each row says why in plain words and opens the review.

import type { MouseEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { useReviews } from "../api/hooks";
import type { Me, RecordingItem } from "../api/types";
import { capitalise, formatWhen } from "../app/format";
import { Button, EmptyState, Icon, PageHeader, Panel, Skeleton, SkeletonGroup, Table } from "../design";

export function ReviewQueuePage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const navigate = useNavigate();
  const reviews = useReviews();
  const rows = reviews.data?.items ?? [];
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
        description={`${capitalise(labels.recording_plural)} Sabha paused on rather than guess. Check each one so it can be scored, or close it.`}
      />
      {reviews.isError ? (
        <Panel>
          <EmptyState
            icon={<Icon name="alert" size={26} />}
            title="We couldn't load the reviews"
            description="Please try again in a moment."
            action={<Button onClick={() => void reviews.refetch()}>Try again</Button>}
          />
        </Panel>
      ) : reviews.isPending ? (
        <Panel>
          <SkeletonGroup label="Loading reviews" className="flex flex-col gap-3">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-4 w-1/3" />
          </SkeletonGroup>
        </Panel>
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
