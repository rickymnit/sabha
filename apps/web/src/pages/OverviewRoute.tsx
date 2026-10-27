// /overview (UI v2, docs/design/v2/01-overview.png) for owners, admins, managers and reviewers: the period's numbers
// and coaching table (features/overview), what needs a decision (GET /v1/inbox), what is being processed right now
// and the newest recordings with who spoke when. Everything comes from the API, for what the signed-in person may
// see.

import { useState, type MouseEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { useInbox, useOverview, useRecordings } from "../api/hooks";
import type { Me, RecordingItem } from "../api/types";
import { capitalise, formatWhen } from "../app/format";
import { RESOLVERS } from "../app/nav";
import {
  Avatar,
  Button,
  EmptyState,
  Icon,
  Panel,
  ScoreChip,
  SpeakerStrip,
  Table,
  cx,
  staffShare,
  type ConversationType,
} from "../design";
import { InboxList } from "../features/inbox/InboxList";
import { ALL_UNITS } from "../features/overview/metrics";
import { OverviewPage } from "../features/overview/OverviewPage";
import { presetRange, toQuery, type DayRange, type RangePreset } from "../features/overview/range";
import type { OverviewStats, ProcessingItem } from "../features/overview/types";

const DECISIONS_SHOWN = 4;

/** The five steps a recording goes through, as the processing bars draw them. */
const STEPS = ["Upload", "Clean", "Speakers", "Transcript", "Scoring"] as const;
const STEP_OF: Record<ProcessingItem["stage"], number> = {
  uploading: 0,
  queued: 1,
  preparing: 1,
  finding_speakers: 2,
  transcribing: 3,
  analysing: 4,
  needs_review: 4,
};

const COMPARE: Record<RangePreset, string> = {
  "7d": "last week",
  "30d": "the 30 days before",
  month: "last month",
  custom: "the period before",
};

const clock = (ms: number | null) => {
  if (ms === null) return "";
  const s = Math.round(ms / 1000);
  const h = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};

function useOpen() {
  const navigate = useNavigate();
  return (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(to);
  };
}

function Decisions({ me }: { me: Me }) {
  const inbox = useInbox();
  const open = useOpen();
  const items = inbox.data?.items ?? [];
  const resolver = RESOLVERS.includes(me.user.role);
  return (
    <Panel
      flush
      title="Needs your decision"
      actions={
        resolver && (
          <a href="/reviews" onClick={(e) => open(e, "/reviews")} className="text-sm font-semibold no-underline">
            Open reviews
          </a>
        )
      }
    >
      {inbox.isError ? (
        <p className="m-0 px-5 py-4 text-sm text-muted">We couldn't load this. Please try again in a moment.</p>
      ) : items.length === 0 ? (
        <p className="m-0 px-5 py-4 text-sm text-muted">{inbox.isSuccess ? "Nothing is waiting for you." : " "}</p>
      ) : (
        <>
          <InboxList items={items.slice(0, DECISIONS_SHOWN)} me={me} />
          {items.length > DECISIONS_SHOWN && (
            <p className="m-0 border-t border-line-subtle px-5 py-3 text-sm text-muted">
              And {items.length - DECISIONS_SHOWN} more under the bell at the top.
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

function Processing({ stats, typeNames }: { stats: OverviewStats; typeNames: Record<ConversationType, string> }) {
  const items = stats.processing ?? [];
  const running = (stats.in_progress ?? []).filter((s) => s.stage !== "needs_review").reduce((n, s) => n + s.n, 0);
  const typical = [...(stats.turnaround ?? [])].sort((a, b) => b.n - a.n)[0];
  return (
    <Panel
      title="Processing now"
      actions={
        typical && (
          <span className="text-small text-muted">
            Typical {typeNames[typical.type].toLowerCase()}: {Math.round(typical.minutes)} min
          </span>
        )
      }
    >
      {items.length === 0 ? (
        <p className="m-0 text-sm text-muted">Nothing is being processed right now.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-3.5 p-0">
          {items.map((item) => {
            const step = STEP_OF[item.stage];
            return (
              <li key={item.id} className="flex flex-col gap-1.5">
                <span className="flex justify-between gap-3 text-sm">
                  <span className="truncate font-semibold text-ink">{item.title}</span>
                  <span className="shrink-0 text-muted">{STEPS[step]}</span>
                </span>
                <span
                  role="img"
                  aria-label={`Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`}
                  className="flex gap-1"
                >
                  {STEPS.map((name, i) => (
                    <span
                      key={name}
                      className={cx(
                        "h-1 flex-1 rounded-full",
                        i < step ? "bg-primary" : i === step ? "bg-primary-border" : "bg-track",
                      )}
                    />
                  ))}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="m-0 text-caption text-muted">
        {running > items.length ? `${running - items.length} more in progress. ` : ""}
        {STEPS.join(", ")}
      </p>
    </Panel>
  );
}

function Recent({ me }: { me: Me }) {
  const labels = me.tenant.labels;
  const open = useOpen();
  const recordings = useRecordings({}, 6);
  const rows = recordings.data?.pages[0]?.items ?? [];
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  const things = labels.recording_plural.toLowerCase();
  const navigate = useNavigate();
  return (
    <Panel
      flush
      title={`Recent ${things}`}
      actions={
        rows.length > 0 && (
          <a href="/recordings" onClick={(e) => open(e, "/recordings")} className="text-sm font-semibold no-underline">
            All {things}
          </a>
        )
      }
    >
      {recordings.isSuccess && rows.length === 0 ? (
        <EmptyState
          headingAs="h3"
          title={`No ${things} yet`}
          action={<Button onClick={() => navigate("/upload")}>Upload</Button>}
        />
      ) : (
        <Table<RecordingItem>
          aria-label={`Recent ${things}`}
          rows={rows}
          rowKey={(r) => r.id}
          minWidth={0}
          rowClassName="relative hover:bg-surface-faint"
          columns={[
            {
              key: "title",
              header: capitalise(labels.recording),
              render: (r) => (
                <div className="flex items-center gap-3">
                  <Avatar name={r.person?.name ?? r.title} size={32} />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <a
                      href={`/recordings/${r.id}`}
                      onClick={(e) => open(e, `/recordings/${r.id}`)}
                      className="font-semibold text-ink no-underline after:absolute after:inset-0 hover:text-primary-hover"
                    >
                      {r.title}
                    </a>
                    <span className="text-small text-muted">
                      {[r.person?.name, r.unit_id ? units.get(r.unit_id) : undefined].filter(Boolean).join(", ")}
                    </span>
                  </div>
                </div>
              ),
            },
            {
              key: "speakers",
              header: "Who spoke when",
              hideOnPhone: true,
              className: "w-[34%] min-w-[140px]",
              render: (r) => {
                const segments = r.speaker_strip ?? [];
                const share = staffShare(segments);
                return (
                  <SpeakerStrip
                    size="row"
                    segments={segments}
                    durationMs={r.duration_ms ?? 0}
                    label={
                      share === null
                        ? "No speaker data yet"
                        : `${capitalise(labels.person)} ${Math.round(share * 100)}% of speech, others ${100 - Math.round(share * 100)}%`
                    }
                  />
                );
              },
            },
            {
              key: "length",
              header: "Length",
              hideOnPhone: true,
              className: "whitespace-nowrap tabular-nums",
              render: (r) => clock(r.duration_ms),
            },
            {
              key: "score",
              header: "Score",
              align: "right",
              render: (r) => <ScoreChip score={r.overall_score} decimals={1} />,
            },
            {
              key: "when",
              header: "When",
              align: "right",
              hideOnPhone: true,
              className: "whitespace-nowrap",
              render: (r) => formatWhen(r.created_at),
            },
          ]}
        />
      )}
    </Panel>
  );
}

export function OverviewRoute() {
  const me = useOutletContext<Me>();
  const [preset, setPreset] = useState<RangePreset>("7d");
  const [range, setRange] = useState<DayRange>(() => presetRange("7d", new Date()));
  const [unit, setUnit] = useState(ALL_UNITS);
  const overview = useOverview(toQuery(range), unit === ALL_UNITS ? null : unit);
  const inbox = useInbox();
  const typeNames = Object.fromEntries(
    (["teaching", "reception", "counselling", "meeting", "sales"] as ConversationType[]).map((t) => [t, capitalise(t)]),
  ) as Record<ConversationType, string>;

  if (overview.isError) {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name="alert" size={26} />}
          title="We couldn't load the overview"
          description="Please try again in a moment."
          action={<Button onClick={() => void overview.refetch()}>Try again</Button>}
        />
      </Panel>
    );
  }
  return (
    <OverviewPage
      stats={overview.data}
      name={me.user.name.split(" ")[0] ?? me.user.name}
      preset={preset}
      range={range}
      onRangeChange={(p, r) => {
        setPreset(p);
        setRange(r);
      }}
      compare={COMPARE[preset]}
      unit={unit}
      onUnitChange={setUnit}
      typeNames={typeNames}
      labels={me.tenant.labels}
      enabledTypes={me.tenant.enabled_types as ConversationType[]}
      waiting={inbox.data?.items.length}
      decisions={<Decisions me={me} />}
      processing={overview.data && <Processing stats={overview.data} typeNames={typeNames} />}
      recent={<Recent me={me} />}
    />
  );
}
