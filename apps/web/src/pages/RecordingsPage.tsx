// /recordings (docs/design/01-overview.png, "Recent recordings"): the recordings the signed-in person may see,
// newest first. Each row names the recording, who it is of and where; the status says in plain words why one
// stopped. Search and the type tabs filter the loaded rows; ?type= keeps the tab in the address. The list
// refreshes while any recording is still being processed (api/hooks.ts).

import { useState, type MouseEvent } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import { useBulkReanalyse, useErasure, usePeople, useRecordings } from "../api/hooks";
import type { Me, RecordingItem } from "../api/types";
import {
  Button,
  EmptyState,
  Icon,
  Input,
  PageHeader,
  Panel,
  ScoreChip,
  SegmentedControl,
  Skeleton,
  SkeletonGroup,
  StatusChip,
  Table,
  TypeDot,
  useToast,
} from "../design";
import { EraseDialog } from "../features/erasure/EraseDialog";
import { BulkReanalyseDialog } from "../features/reanalysis";
import { capitalise, formatWhen, statusChip } from "../app/format";
import { formatClock } from "../features/transcript/text";

/** Whose recordings the page shows, in the subtitle. */
function scope(me: Me): string {
  const things = me.tenant.labels.recording_plural.toLowerCase();
  if (me.user.role === "staff") return `Your ${things}, newest first.`;
  if (me.user.role === "manager" || me.user.role === "reviewer") {
    const byId = new Map(me.tenant.units.map((u) => [u.id, u.name]));
    const names = me.user.unit_ids.map((id) => byId.get(id)).filter(Boolean);
    if (names.length) return `${capitalise(things)} from ${names.join(", ")}, newest first.`;
  }
  return `Every ${me.tenant.labels.recording.toLowerCase()} in ${me.tenant.name}, newest first.`;
}

export function RecordingsPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const personParam = params.get("person");
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));

  const types = me.tenant.enabled_types;
  const typeParam = params.get("type");
  const type = typeParam && types.includes(typeParam as never) ? typeParam : "all";
  const setFilters = (next: { type?: string; person?: string | null }) => {
    const nextType = next.type ?? type;
    const nextPerson = next.person === undefined ? personParam : next.person;
    setParams(
      { ...(nextType !== "all" ? { type: nextType } : {}), ...(nextPerson ? { person: nextPerson } : {}) },
      { replace: true, preventScrollReset: true },
    );
  };
  const setType = (value: string) => setFilters({ type: value });
  // Type and person are narrowed by the API, so they hold across pages; search filters the loaded rows.
  const recordings = useRecordings({ type: type === "all" ? null : type, personId: personParam });
  const personName = recordings.data?.pages[0]?.items[0]?.person?.name;

  const all = recordings.data?.pages.flatMap((page) => page.items) ?? [];
  const needle = query.trim().toLowerCase();
  const rows = all.filter(
    (r) =>
      !needle || r.title.toLowerCase().includes(needle) || (r.person?.name.toLowerCase().includes(needle) ?? false),
  );
  const filtered = type !== "all" || needle !== "" || personParam !== null;
  const things = labels.recording_plural.toLowerCase();

  const open = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(`/recordings/${id}`);
  };
  const toast = useToast();
  const bulk = useBulkReanalyse();
  const [bulkOpen, setBulkOpen] = useState(false);
  const isAdmin = me.user.role === "owner" || me.user.role === "admin";
  const isOwner = me.user.role === "owner";
  const people = usePeople();
  const erasure = useErasure();
  const [erasing, setErasing] = useState(false);
  const chosenPerson = personParam ? people.data?.find((p) => p.id === personParam) : undefined;
  const upload = (
    <Button icon={<Icon name="upload" />} onClick={() => navigate("/upload")}>
      Upload
    </Button>
  );
  const actions = (
    <span className="flex flex-wrap gap-2">
      {isAdmin && (
        <Button variant="secondary" onClick={() => setBulkOpen(true)}>
          Re-analyse…
        </Button>
      )}
      {upload}
    </span>
  );
  const bulkDialog = bulkOpen && (
    <BulkReanalyseDialog
      types={types}
      recordingsWord={labels.recording_plural.toLowerCase()}
      typeLabel={capitalise}
      run={bulk.mutateAsync}
      onStarted={(result) =>
        toast.show({
          tone: "success",
          title: `Re-analysing ${result.started}`,
          message:
            result.remaining > 0
              ? `${result.remaining} more can be started with another click. New reports appear in a few minutes.`
              : "New reports appear in a few minutes; earlier ones are kept.",
          duration: 8_000,
        })
      }
      onClose={() => setBulkOpen(false)}
    />
  );

  if (recordings.isSuccess && all.length === 0 && !filtered) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={capitalise(labels.recording_plural)} description={scope(me)} />
        <Panel>
          <EmptyState
            className="py-14"
            icon={<Icon name="recordings" size={26} />}
            title={`No ${things} yet`}
            description={`Upload a recording and Sabha will write the transcript, tell the speakers apart and give feedback with quotes from the ${labels.recording.toLowerCase()}.`}
            action={upload}
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={capitalise(labels.recording_plural)}
        description={personParam && personName ? `${personName}’s ${things}, newest first.` : scope(me)}
        actions={actions}
      />
      {bulkDialog}
      {personParam && (
        <div className="-mt-2 flex">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface py-1 pl-3 pr-1 text-sm">
            {personName ?? capitalise(labels.person)}
            <Button
              variant="ghost"
              aria-label="Show everyone"
              title="Show everyone"
              onClick={() => setFilters({ person: null })}
              className="min-h-0 min-w-0 rounded-full p-1"
            >
              <Icon name="close" size={14} />
            </Button>
          </span>
          {isOwner && chosenPerson && (
            <Button variant="ghost" className="ml-auto text-danger" onClick={() => setErasing(true)}>
              Erase all of {chosenPerson.name}’s data
            </Button>
          )}
        </div>
      )}
      {erasing && chosenPerson && (
        <EraseDialog
          what={`all of ${chosenPerson.name}’s data`}
          confirmName={chosenPerson.name}
          recordingWord={labels.recording.toLowerCase()}
          recordingsWord={things}
          run={(confirm, reason) => erasure.mutateAsync({ scope: "person", id: chosenPerson.id, reason, confirm })}
          onErased={() => {
            setErasing(false);
            toast.show({ tone: "success", title: `${chosenPerson.name}’s data was erased`, duration: 6_000 });
            setFilters({ person: null });
          }}
          onClose={() => setErasing(false)}
        />
      )}
      {recordings.isError ? (
        <Panel>
          <EmptyState
            icon={<Icon name="alert" size={26} />}
            title={`We couldn't load your ${things}`}
            description="Please try again in a moment."
            action={<Button onClick={() => void recordings.refetch()}>Try again</Button>}
          />
        </Panel>
      ) : (
        <Panel
          flush
          aria-label={capitalise(labels.recording_plural)}
          actions={
            <div className="flex w-full flex-wrap items-center justify-between gap-3">
              <Input
                label={`Search ${things}`}
                hideLabel
                type="search"
                placeholder={`Search by title or ${labels.person.toLowerCase()}`}
                leadingIcon={<Icon name="search" size={16} />}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full sm:w-80"
              />
              {types.length > 1 && (
                <SegmentedControl
                  label="Filter by type"
                  value={type}
                  onChange={setType}
                  options={[{ value: "all", label: "All" }, ...types.map((t) => ({ value: t, label: capitalise(t) }))]}
                />
              )}
            </div>
          }
          footer={
            recordings.isSuccess && (
              <>
                <span>
                  Showing {rows.length} {rows.length === 1 ? labels.recording.toLowerCase() : things}
                </span>
                {recordings.hasNextPage && (
                  <Button
                    variant="secondary"
                    disabled={recordings.isFetchingNextPage}
                    onClick={() => void recordings.fetchNextPage()}
                  >
                    {recordings.isFetchingNextPage ? "Loading…" : `Show older ${things}`}
                  </Button>
                )}
              </>
            )
          }
        >
          {recordings.isPending ? (
            <SkeletonGroup label={`Loading ${things}`} className="flex flex-col gap-4 px-5 py-5">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="flex items-center gap-6">
                  <div className="flex flex-1 flex-col gap-2">
                    <Skeleton className="h-4 w-2/5" />
                    <Skeleton className="h-3 w-1/4" />
                  </div>
                  <Skeleton className="h-6 w-24" />
                  <Skeleton className="h-4 w-12" />
                </div>
              ))}
            </SkeletonGroup>
          ) : (
            <Table<RecordingItem>
              aria-label={capitalise(labels.recording_plural)}
              rows={rows}
              rowKey={(r) => r.id}
              minWidth={0}
              rowClassName="relative hover:bg-surface-faint"
              empty={
                filtered ? (
                  <EmptyState
                    headingAs="h3"
                    title={`No ${things} match`}
                    description="Try a different search or type."
                    action={
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setQuery("");
                          setFilters({ type: "all", person: null });
                        }}
                      >
                        Clear filters
                      </Button>
                    }
                  />
                ) : undefined
              }
              columns={[
                {
                  key: "title",
                  header: capitalise(labels.recording),
                  render: (r) => (
                    <div className="flex flex-col gap-0.5">
                      <a
                        href={`/recordings/${r.id}`}
                        onClick={(e) => open(e, r.id)}
                        className="font-semibold text-ink no-underline after:absolute after:inset-0 hover:text-primary-hover"
                      >
                        {r.title}
                      </a>
                      <span className="text-small text-muted">
                        {[r.person?.name, r.unit_id ? units.get(r.unit_id) : undefined].filter(Boolean).join(", ") ||
                          "—"}
                      </span>
                      <span className="text-caption text-muted-2 md:hidden">{formatWhen(r.created_at)}</span>
                    </div>
                  ),
                },
                {
                  key: "type",
                  hideOnPhone: true,
                  header: "Type",
                  render: (r) => <TypeDot type={r.type} label={capitalise(r.type)} />,
                },
                {
                  key: "length",
                  hideOnPhone: true,
                  header: "Length",
                  render: (r) => (r.duration_ms === null ? "—" : formatClock(r.duration_ms)),
                },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => {
                    const { chip, text } = statusChip(r.status);
                    return (
                      <div className="flex flex-col items-start gap-1">
                        <StatusChip status={chip}>{text}</StatusChip>
                        {r.status_note && (
                          <span className="max-w-[30ch] text-caption leading-snug text-muted">{r.status_note}</span>
                        )}
                      </div>
                    );
                  },
                },
                {
                  key: "score",
                  header: "Score",
                  align: "right",
                  render: (r) => <ScoreChip score={r.overall_score} variant="text" decimals={1} />,
                },
                {
                  key: "uploaded",
                  hideOnPhone: true,
                  header: "Uploaded",
                  align: "right",
                  className: "whitespace-nowrap",
                  render: (r) => formatWhen(r.created_at),
                },
              ]}
            />
          )}
        </Panel>
      )}
    </div>
  );
}
