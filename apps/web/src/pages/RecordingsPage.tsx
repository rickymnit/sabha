// /recordings (UI v2, docs/design/v2/02-recordings.png): every recording the signed-in person may see, newest first,
// ten to a page. Tabs (all, needs your decision, each type, scored below 3) and filters (type, unit, person, when
// recorded, score band) are narrowed by the API and kept in the address, so the sidebar's type links and a shared
// link open the same list. Rows show who spoke when, the score and the status; a failed one that can still be
// retried has Retry and Close. Ticking rows opens the bulk bar: re-analyse (owners and admins) and share with the
// people analysed. "Export list" downloads the same filtered list as CSV.

import { useMemo, useState, type MouseEvent, type ReactNode } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import {
  useErasure,
  useExportRecordings,
  useFailedRecordingAction,
  usePeople,
  useReanalyseMany,
  useRecordingCounts,
  useRecordingsPage,
  useRubrics,
  useShareRecordings,
} from "../api/hooks";
import type { Me, RecordingItem, RecordingQuery } from "../api/types";
import { RESOLVERS } from "../app/nav";
import { capitalise, formatWhen, statusChip } from "../app/format";
import { othersWord, staffWord } from "../app/speakerWords";
import { unitTree } from "../app/units";
import {
  Avatar,
  Button,
  EmptyState,
  Icon,
  PageHeader,
  Panel,
  ScoreChip,
  Skeleton,
  SkeletonGroup,
  SpeakerLegend,
  SpeakerStrip,
  StatusChip,
  Table,
  TypeDot,
  cx,
  staffShare,
  useToast,
  type ConversationType,
} from "../design";
import { EraseDialog } from "../features/erasure/EraseDialog";
import { presetRange } from "../features/overview/range";
import { ReasonDialog } from "../features/processing/ReasonDialog";
import { ReanalyseDialog } from "../features/reanalysis/ReanalyseDialog";
import { ShareDialog } from "../features/share/ShareDialog";
import { formatClock } from "../features/transcript/text";

const PAGE_SIZE = 10;
/** A secondary button on the dark bulk bar. */
const INVERSE =
  "border-white/25 bg-transparent text-surface hover:bg-white/10 disabled:bg-transparent disabled:opacity-50";
const SCORES = { below_3: "Below 3.0", mid: "3.0 to 3.79", good: "3.8 and above" } as const;
const RECORDED = { "7d": "Last 7 days", "30d": "Last 30 days", month: "This month" } as const;
type Score = keyof typeof SCORES;
type Recorded = keyof typeof RECORDED;
type Tab = "all" | "decision" | "below_3" | ConversationType;

const count = (n: number | null | undefined) => (typeof n === "number" ? n.toLocaleString("en-IN") : undefined);

/** A filter that looks like the design's pill ("Type All ▾") and is a native <select> underneath. */
function FilterPill<V extends string>(props: {
  label: string;
  value: V;
  options: { value: V; label: string }[];
  onChange: (value: V) => void;
}) {
  const chosen = props.options.find((o) => o.value === props.value);
  const active = props.value !== props.options[0]?.value;
  return (
    <label
      className={cx(
        "relative inline-flex min-h-[36px] items-center gap-1.5 rounded-full border px-3.5 text-sm",
        active ? "border-primary-border bg-primary-tint" : "border-line bg-surface",
      )}
    >
      <span className="text-muted">{props.label}</span>
      <span className="font-semibold text-ink">{chosen?.label}</span>
      <Icon name="chevronDown" size={14} className="text-muted" />
      <select
        value={props.value}
        onChange={(e) => props.onChange(e.target.value as V)}
        className="absolute inset-0 cursor-pointer opacity-0"
        aria-label={props.label}
      >
        {props.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Retry and Close under a failed row, for owners and admins; each asks why first. */
function FailedActions({ recording, things }: { recording: RecordingItem; things: string }) {
  const [asking, setAsking] = useState<"retry" | "abandon" | null>(null);
  const retry = useFailedRecordingAction(recording.id, "retry");
  const abandon = useFailedRecordingAction(recording.id, "abandon");
  const toast = useToast();
  return (
    <span className="relative z-10 flex gap-1.5">
      <Button variant="secondary" className="min-h-[32px] px-2.5 text-small" onClick={() => setAsking("retry")}>
        Retry
      </Button>
      <Button variant="secondary" className="min-h-[32px] px-2.5 text-small" onClick={() => setAsking("abandon")}>
        Close
      </Button>
      {asking && (
        <ReasonDialog
          title={asking === "retry" ? `Retry “${recording.title}”` : `Close “${recording.title}”`}
          description={
            asking === "retry"
              ? "Sabha runs the step that failed again; earlier steps are not repeated."
              : `It stays failed and leaves the ${things} that need a decision. It cannot be retried later.`
          }
          submitLabel={asking === "retry" ? "Retry" : "Close"}
          onSubmit={async (reason) => {
            await (asking === "retry" ? retry : abandon).mutateAsync(reason);
            toast.show({ tone: "success", title: asking === "retry" ? "Started again" : "Closed", duration: 5_000 });
          }}
          onClose={() => setAsking(null)}
        />
      )}
    </span>
  );
}

export function RecordingsPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const things = labels.recording_plural.toLowerCase();
  const navigate = useNavigate();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const types = me.tenant.enabled_types;
  const isAdmin = me.user.role === "owner" || me.user.role === "admin";
  const canShare = me.user.role !== "staff";
  const canDecide = RESOLVERS.includes(me.user.role) || isAdmin;

  // The address holds the filters: ?type=, person=, unit=, score=, recorded=, tab=decision.
  const read = <T extends string>(key: string, allowed: readonly string[]): T | null => {
    const v = params.get(key);
    return v && allowed.includes(v) ? (v as T) : null;
  };
  const type = read<ConversationType>("type", types);
  const personId = params.get("person");
  const unitId = params.get("unit");
  const score = read<Score>("score", Object.keys(SCORES));
  const recorded = read<Recorded>("recorded", Object.keys(RECORDED));
  const decision = params.get("tab") === "decision";
  const set = (next: Record<string, string | null>) => {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value);
      else merged.delete(key);
    }
    setParams(merged, { replace: true, preventScrollReset: true });
    setCursors([null]);
    setSelected(new Set());
  };

  const query: RecordingQuery = useMemo(() => {
    const range = recorded ? presetRange(recorded, new Date()) : null;
    return {
      type,
      person_id: personId,
      unit_id: unitId,
      score,
      recorded_from: range?.start ?? null,
      recorded_to: range?.end ?? null,
      tab: decision ? "decision" : null,
    };
  }, [type, personId, unitId, score, recorded, decision]);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const page = useRecordingsPage(query, cursors.at(-1) ?? null, PAGE_SIZE);
  const counts = useRecordingCounts();
  const people = usePeople();
  const rubrics = useRubrics();
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  const topUnits = unitTree(me.tenant.units);
  const rows = page.data?.items ?? [];
  const filtered = Boolean(type || personId || unitId || score || recorded || decision);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const chosen = rows.filter((r) => selected.has(r.id));
  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const [sharing, setSharing] = useState(false);
  const [reanalysing, setReanalysing] = useState(false);
  const share = useShareRecordings();
  const reanalyse = useReanalyseMany();
  const exporting = useExportRecordings();
  const erasure = useErasure();
  const [erasing, setErasing] = useState(false);
  const chosenPerson = personId ? people.data?.find((p) => p.id === personId) : undefined;

  const tab: Tab = decision ? "decision" : type && !score ? type : score === "below_3" && !type ? "below_3" : "all";
  const tabs: { value: Tab; label: string; n: string | undefined; to: Record<string, string | null> }[] = [
    {
      value: "all",
      label: "All",
      n: count(counts.data?.total),
      to: { tab: null, type: null, score: null },
    },
    ...(canDecide
      ? [
          {
            value: "decision" as Tab,
            label: "Needs your decision",
            n: count(counts.data?.needs_decision),
            to: { tab: "decision", type: null, score: null },
          },
        ]
      : []),
    ...(types.length > 1
      ? types.map((t) => ({
          value: t as Tab,
          label: capitalise(t),
          n: count(counts.data?.by_type?.[t] ?? 0),
          to: { tab: null, type: t, score: null },
        }))
      : []),
    {
      value: "below_3",
      label: "Scored below 3",
      n: count(counts.data?.below_3),
      to: { tab: null, type: null, score: "below_3" },
    },
  ];
  const tabTotal = { all: counts.data?.total, decision: counts.data?.needs_decision, below_3: counts.data?.below_3 };
  const shownOf =
    tab === "all" && filtered
      ? undefined
      : tab in tabTotal
        ? tabTotal[tab as keyof typeof tabTotal]
        : counts.data?.by_type?.[tab as ConversationType];
  const onlyTab = !personId && !unitId && !recorded && (tab !== "all" || !filtered) && (!score || tab === "below_3");

  const open = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(`/recordings/${id}`);
  };
  const versionFor = (t: string) => {
    const item = rubrics.data?.items.find((r) => r.type === t);
    return item?.versions.find((v) => v.id === item.current_id)?.version;
  };
  const chosenTypes = [...new Set(chosen.map((r) => r.type))];
  const bulkVersion = chosenTypes.length === 1 && chosenTypes[0] ? versionFor(chosenTypes[0]) : undefined;
  const sharable = chosen.filter((r) => r.status === "COMPLETED" && r.person);

  const upload = (
    <Button icon={<Icon name="upload" />} onClick={() => navigate("/upload")}>
      Upload
    </Button>
  );

  if (page.isSuccess && rows.length === 0 && !filtered && cursors.length === 1) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={capitalise(labels.recording_plural)} description={`No ${things} yet.`} />
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

  const columns = [
    ...(canShare
      ? [
          {
            key: "select",
            header: (
              <input
                type="checkbox"
                aria-label={`Select every ${labels.recording.toLowerCase()} on this page`}
                checked={rows.length > 0 && rows.every((r) => selected.has(r.id))}
                onChange={(e) => setSelected(e.target.checked ? new Set(rows.map((r) => r.id)) : new Set())}
                className="size-4 accent-primary"
              />
            ),
            className: "w-10",
            render: (r: RecordingItem) => (
              <input
                type="checkbox"
                aria-label={`Select ${r.title}`}
                checked={selected.has(r.id)}
                onChange={() => toggle(r.id)}
                className="relative z-10 size-4 accent-primary"
              />
            ),
          },
        ]
      : []),
    {
      key: "title",
      header: capitalise(labels.recording),
      render: (r: RecordingItem) => (
        <div className="flex items-center gap-3">
          <Avatar name={r.person?.name ?? r.title} size={32} className="shrink-0" />
          <div className="flex min-w-0 flex-col gap-0.5">
            <a
              href={`/recordings/${r.id}`}
              onClick={(e) => open(e, r.id)}
              className="font-semibold text-ink no-underline after:absolute after:inset-0 hover:text-primary-hover"
            >
              {r.title}
            </a>
            <span className="text-small text-muted">
              {[r.person?.name, r.unit_id ? units.get(r.unit_id) : undefined].filter(Boolean).join(", ") || "—"}
            </span>
            <span className="text-caption text-muted-2 md:hidden">{formatWhen(r.recorded_at ?? r.created_at)}</span>
          </div>
        </div>
      ),
    },
    {
      key: "type",
      hideOnPhone: true,
      header: "Type",
      className: "whitespace-nowrap",
      render: (r: RecordingItem) => <TypeDot type={r.type} label={capitalise(r.type)} />,
    },
    {
      key: "speakers",
      header: "Who spoke when",
      hideOnPhone: true,
      className: "w-[16%] min-w-[110px]",
      render: (r: RecordingItem) => {
        const segments = r.speaker_strip ?? [];
        const share = staffShare(segments);
        const word = staffWord(r.type, labels);
        return (
          <SpeakerStrip
            size="row"
            segments={segments}
            durationMs={r.duration_ms ?? 0}
            label={share === null ? "No speaker data yet" : `${word} ${Math.round(share * 100)}% of speech`}
            {...(share === null ? {} : { caption: `${word} ${Math.round(share * 100)}%` })}
          />
        );
      },
    },
    {
      key: "length",
      hideOnPhone: true,
      header: "Length",
      className: "whitespace-nowrap tabular-nums",
      render: (r: RecordingItem) => (r.duration_ms === null ? "—" : formatClock(r.duration_ms)),
    },
    {
      key: "score",
      header: "Score",
      render: (r: RecordingItem) => <ScoreChip score={r.overall_score} decimals={1} />,
    },
    {
      key: "status",
      header: "Status",
      render: (r: RecordingItem) => {
        const { chip, text } = statusChip(r.status);
        return (
          <div className="flex flex-col items-start gap-1">
            <StatusChip status={chip}>{text}</StatusChip>
            {r.status_note && (
              <span className="max-w-[26ch] text-caption leading-snug text-muted">{r.status_note}</span>
            )}
            {isAdmin && r.retryable && <FailedActions recording={r} things={things} />}
          </div>
        );
      },
    },
    {
      key: "recorded",
      hideOnPhone: true,
      header: "Recorded",
      align: "right" as const,
      className: "whitespace-nowrap",
      render: (r: RecordingItem) => formatWhen(r.recorded_at ?? r.created_at),
    },
  ];

  let body: ReactNode;
  if (page.isError) {
    body = (
      <EmptyState
        icon={<Icon name="alert" size={26} />}
        title={`We couldn't load your ${things}`}
        description="Please try again in a moment."
        action={<Button onClick={() => void page.refetch()}>Try again</Button>}
      />
    );
  } else if (page.isPending) {
    body = (
      <SkeletonGroup label={`Loading ${things}`} className="flex flex-col gap-4 px-5 py-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center gap-6">
            <Skeleton className="size-8 rounded-full" />
            <div className="flex flex-1 flex-col gap-2">
              <Skeleton className="h-4 w-2/5" />
              <Skeleton className="h-3 w-1/4" />
            </div>
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-4 w-12" />
          </div>
        ))}
      </SkeletonGroup>
    );
  } else {
    body = (
      <Table<RecordingItem>
        aria-label={capitalise(labels.recording_plural)}
        rows={rows}
        rowKey={(r) => r.id}
        minWidth={0}
        rowClassName={(r: RecordingItem) =>
          cx("relative hover:bg-surface-faint", selected.has(r.id) && "bg-primary-tint/40")
        }
        empty={
          <EmptyState
            headingAs="h3"
            title={decision ? "Nothing needs your decision" : `No ${things} match`}
            description={decision ? "Everything has been reviewed." : "Try a different tab or filter."}
            action={
              filtered ? (
                <Button
                  variant="secondary"
                  onClick={() => set({ type: null, person: null, unit: null, score: null, recorded: null, tab: null })}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        }
        columns={columns}
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={capitalise(labels.recording_plural)}
        description={
          counts.data?.total !== undefined
            ? `${count(counts.data.total)} ${counts.data.total === 1 ? labels.recording.toLowerCase() : things}, newest first`
            : "Newest first"
        }
        actions={
          <Button
            variant="secondary"
            icon={<Icon name="download" />}
            disabled={exporting.isPending}
            onClick={() =>
              exporting.mutate(query, {
                onError: () => toast.show({ tone: "error", title: "The list could not be exported" }),
              })
            }
          >
            {exporting.isPending ? "Exporting…" : "Export list"}
          </Button>
        }
      />

      <nav aria-label="Views" className="-mt-1 flex gap-6 overflow-x-auto border-b border-line">
        {tabs.map((t) => (
          <button
            key={t.value}
            type="button"
            aria-current={tab === t.value ? "page" : undefined}
            onClick={() => set(t.to)}
            className={cx(
              "-mb-px flex min-h-[44px] shrink-0 items-center gap-1.5 border-b-2 bg-transparent px-0.5 text-sm",
              tab === t.value
                ? "border-primary font-semibold text-ink"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t.label}
            {t.n !== undefined && <span className="text-caption tabular-nums text-muted-2">{t.n}</span>}
          </button>
        ))}
      </nav>

      <div className="flex flex-wrap items-center gap-2">
        {types.length > 1 && (
          <FilterPill
            label="Type"
            value={type ?? "all"}
            options={[{ value: "all", label: "All" }, ...types.map((t) => ({ value: t, label: capitalise(t) }))]}
            onChange={(v) => set({ type: v === "all" ? null : v, tab: null })}
          />
        )}
        {topUnits.length > 1 && (
          <FilterPill
            label={capitalise(labels.unit_group ?? labels.unit)}
            value={unitId ?? "all"}
            options={[{ value: "all", label: "All" }, ...topUnits.map((u) => ({ value: u.id, label: u.name }))]}
            onChange={(v) => set({ unit: v === "all" ? null : v })}
          />
        )}
        {me.user.role !== "staff" && (
          <FilterPill
            label={capitalise(labels.person)}
            value={personId ?? "all"}
            options={[
              { value: "all", label: "Anyone" },
              ...(people.data ?? []).map((p) => ({ value: p.id, label: p.name })),
            ]}
            onChange={(v) => set({ person: v === "all" ? null : v })}
          />
        )}
        <FilterPill
          label="Recorded"
          value={recorded ?? "any"}
          options={[
            { value: "any", label: "Any time" },
            ...Object.entries(RECORDED).map(([value, label]) => ({ value, label })),
          ]}
          onChange={(v) => set({ recorded: v === "any" ? null : v })}
        />
        <FilterPill
          label="Score"
          value={score ?? "any"}
          options={[
            { value: "any", label: "Any" },
            ...Object.entries(SCORES).map(([value, label]) => ({ value, label })),
          ]}
          onChange={(v) => set({ score: v === "any" ? null : v })}
        />
        {filtered && (
          <Button
            variant="ghost"
            onClick={() => set({ type: null, person: null, unit: null, score: null, recorded: null, tab: null })}
          >
            Clear filters
          </Button>
        )}
        <SpeakerLegend staff="Staff speaking" others={othersWord(types)} className="ml-auto" />
      </div>

      {isAdmin && chosenPerson && (
        <div className="-mt-2 flex justify-end">
          <Button variant="ghost" className="text-danger" onClick={() => setErasing(true)}>
            Erase all of {chosenPerson.name}’s data
          </Button>
        </div>
      )}

      {chosen.length > 0 && (
        <div
          role="region"
          aria-label="Selected"
          className="flex flex-wrap items-center gap-3 rounded-panel bg-ink px-5 py-3 text-surface"
        >
          <span className="text-sm font-semibold">
            {chosen.length} {chosen.length === 1 ? labels.recording.toLowerCase() : things} selected
          </span>
          <span className="ml-auto flex flex-wrap gap-2">
            {isAdmin && (
              <Button variant="secondary" className={INVERSE} onClick={() => setReanalysing(true)}>
                Re-analyse{bulkVersion ? ` with v${bulkVersion}` : ""}
              </Button>
            )}
            <Button
              variant="secondary"
              className={INVERSE}
              disabled={sharable.length === 0}
              onClick={() => setSharing(true)}
            >
              Share with staff
            </Button>
            <Button variant="ghost" className="text-surface" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
          </span>
        </div>
      )}

      <Panel
        flush
        aria-label={capitalise(labels.recording_plural)}
        footer={
          page.isSuccess && (
            <>
              <span>
                Showing {rows.length}
                {onlyTab && shownOf !== undefined && shownOf !== null ? ` of ${count(shownOf)}` : ""}
              </span>
              {/* Only when there is another page to go to. */}
              {(cursors.length > 1 || Boolean(page.data?.next_cursor)) && (
                <span className="flex gap-2">
                  <Button
                    variant="secondary"
                    disabled={cursors.length === 1}
                    onClick={() => {
                      setCursors((c) => c.slice(0, -1));
                      setSelected(new Set());
                    }}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={!page.data?.next_cursor || page.isPlaceholderData}
                    onClick={() => {
                      setCursors((c) => [...c, page.data?.next_cursor ?? null]);
                      setSelected(new Set());
                    }}
                  >
                    Next
                  </Button>
                </span>
              )}
            </>
          )
        }
      >
        {body}
      </Panel>

      {sharing && (
        <ShareDialog
          who={sharable.length === 1 && sharable[0]?.person ? (sharable[0].person.name.split(" ")[0] ?? "") : "staff"}
          recordingWord={labels.recording.toLowerCase()}
          count={sharable.length}
          onSubmit={async (note) => {
            const out = await share.mutateAsync({ recording_ids: sharable.map((r) => r.id), note });
            toast.show({
              tone: "success",
              title: out.shared.length === 1 ? "Shared" : `Shared ${out.shared.length} reports`,
              message: "They get an email with a link.",
              duration: 6_000,
            });
            setSelected(new Set());
          }}
          onClose={() => setSharing(false)}
        />
      )}
      {reanalysing && (
        <ReanalyseDialog
          recordingWord={labels.recording.toLowerCase()}
          recordingsWord={things}
          count={chosen.length}
          {...(bulkVersion ? { version: `v${bulkVersion}` } : {})}
          onSubmit={async (reason) => {
            const started = await reanalyse.mutateAsync({ ids: chosen.map((r) => r.id), reason });
            toast.show({
              tone: "success",
              title: `Re-analysing ${started}`,
              message: "New reports appear in a few minutes; earlier ones are kept.",
              duration: 8_000,
            });
            setSelected(new Set());
          }}
          onClose={() => setReanalysing(false)}
        />
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
            set({ person: null });
          }}
          onClose={() => setErasing(false)}
        />
      )}
    </div>
  );
}
