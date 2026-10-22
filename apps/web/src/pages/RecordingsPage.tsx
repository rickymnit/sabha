// /recordings (P6.2): the recordings the signed-in person may see, newest first, with status and score. The list
// refreshes while any recording is still being processed (api/hooks.ts). ?type= filters by conversation type.

import type { MouseEvent } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import { useRecordings } from "../api/hooks";
import type { Me, RecordingItem } from "../api/types";
import { Button, EmptyState, PageHeader, ScoreChip, StatusChip, Table, TypeDot } from "../design";
import { capitalise, formatDateTime, formatDuration, statusChip } from "../app/format";

export function RecordingsPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const type = params.get("type");
  const recordings = useRecordings();
  const all = recordings.data?.pages.flatMap((page) => page.items) ?? [];
  const rows = type ? all.filter((r) => r.type === type) : all;

  const open = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(`/recordings/${id}`);
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={capitalise(labels.recording_plural)}
        description={type ? `${capitalise(type)} only` : undefined}
        actions={<Button onClick={() => navigate("/upload")}>Upload</Button>}
      />
      {recordings.isError && <EmptyState title="Could not load the list" description={recordings.error.message} />}
      <Table<RecordingItem>
        aria-label={capitalise(labels.recording_plural)}
        rows={rows}
        rowKey={(r) => r.id}
        minWidth={720}
        empty={
          recordings.isPending
            ? "Loading…"
            : `No ${labels.recording_plural.toLowerCase()} yet. Upload one to get started.`
        }
        columns={[
          {
            key: "title",
            header: capitalise(labels.recording),
            render: (r) => (
              <a href={`/recordings/${r.id}`} onClick={(e) => open(e, r.id)} className="font-semibold text-ink">
                {r.file_name ?? r.id}
              </a>
            ),
          },
          { key: "person", header: capitalise(labels.person), render: (r) => r.person?.name ?? "—" },
          {
            key: "type",
            header: "Type",
            render: (r) => <TypeDot type={r.type} label={capitalise(r.type)} />,
          },
          {
            key: "status",
            header: "Status",
            render: (r) => {
              const { chip, text } = statusChip(r.status);
              return <StatusChip status={chip}>{text}</StatusChip>;
            },
          },
          {
            key: "score",
            header: "Score",
            align: "right",
            render: (r) => <ScoreChip score={r.overall_score} variant="text" />,
          },
          { key: "length", header: "Length", align: "right", render: (r) => formatDuration(r.duration_ms) },
          { key: "uploaded", header: "Uploaded", render: (r) => formatDateTime(r.created_at) },
        ]}
      />
      {recordings.hasNextPage && (
        <Button
          variant="secondary"
          className="self-center"
          disabled={recordings.isFetchingNextPage}
          onClick={() => void recordings.fetchNextPage()}
        >
          {recordings.isFetchingNextPage ? "Loading…" : "Show more"}
        </Button>
      )}
    </div>
  );
}
