// Panels shared by the Overview (pages/OverviewRoute.tsx) and a staff member's own page (pages/MyProgressPage.tsx):
// what is being processed right now, and the newest recordings with who spoke when.

import { useNavigate } from "react-router-dom";

import { useRecordings } from "../../api/hooks";
import type { Me, RecordingItem } from "../../api/types";
import { capitalise, formatWhen } from "../../app/format";
import { useOpen } from "../../app/useOpen";
import { othersWord, staffWord } from "../../app/speakerWords";
import {
  Avatar,
  Button,
  EmptyState,
  Panel,
  ScoreChip,
  SpeakerLegend,
  SpeakerStrip,
  Table,
  cx,
  staffShare,
  type ConversationType,
} from "../../design";
import { formatClock } from "../transcript/text";
import type { OverviewStats, ProcessingItem } from "./types";

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

// The same "1:19" as the recordings list, so one call has one length everywhere.
const clock = (ms: number | null) => (ms === null ? "" : formatClock(ms));

const clockIst = new Intl.DateTimeFormat("en-IN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "Asia/Kolkata",
});

/** "ready about 11:42": upload time plus the type's median turnaround; nothing once that time has passed. */
function readyAbout(item: ProcessingItem, minutes: number | undefined, now: Date): string {
  if (!item.uploaded_at || minutes === undefined || item.stage === "uploading") return "";
  const at = new Date(new Date(item.uploaded_at).getTime() + minutes * 60_000);
  return at > now ? `ready about ${clockIst.format(at)}` : "";
}

export function Processing({
  stats,
  typeNames,
}: {
  stats: OverviewStats;
  typeNames: Record<ConversationType, string>;
}) {
  const items = stats.processing ?? [];
  const running = (stats.in_progress ?? []).filter((s) => s.stage !== "needs_review").reduce((n, s) => n + s.n, 0);
  // The usual wait for each type uploaded, most uploaded first: "Typical support 4 min · sales 5 min".
  const typical = [...(stats.turnaround ?? [])].sort((a, b) => b.n - a.n).slice(0, 3);
  const minutesFor = (type: ConversationType) => stats.turnaround?.find((t) => t.type === type)?.minutes;
  const now = new Date();
  return (
    <Panel
      title="Processing now"
      actions={
        typical.length > 0 && (
          <span className="text-small text-muted">
            Typical {typical.map((t) => `${typeNames[t.type].toLowerCase()} ${Math.round(t.minutes)} min`).join(" · ")}
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
              <li key={item.id} className="flex flex-col gap-1">
                <span className="truncate text-sm font-semibold text-ink">{item.title}</span>
                <span className="text-small text-muted">
                  {[STEPS[step], readyAbout(item, minutesFor(item.type), now)].filter(Boolean).join(", ")}
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

/** How many recent recordings the panels show; the staff page reads the same list (one request). */
export const RECENT_SHOWN = 6;

/**
 * The newest recordings with who spoke when. `mine`: a staff member's own list, so no name or face on every row and
 * the legend says "You".
 */
export function Recent({ me, mine = false }: { me: Me; mine?: boolean }) {
  const labels = me.tenant.labels;
  const open = useOpen();
  const recordings = useRecordings({}, RECENT_SHOWN);
  const rows = recordings.data?.pages[0]?.items ?? [];
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  const things = labels.recording_plural.toLowerCase();
  const navigate = useNavigate();
  return (
    <Panel
      flush
      title={mine ? `Your recent ${things}` : `Recent ${things}`}
      actions={
        rows.length > 0 && (
          <span className="flex flex-wrap items-center gap-4">
            <SpeakerLegend
              staff={mine ? "You speaking" : "Staff speaking"}
              others={othersWord(me.tenant.enabled_types)}
            />
            <a
              href="/recordings"
              onClick={(e) => open(e, "/recordings")}
              className="text-sm font-semibold no-underline"
            >
              All {things}
            </a>
          </span>
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
                  {!mine && <Avatar name={r.person?.name ?? r.title} size={32} />}
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <a
                      href={`/recordings/${r.id}`}
                      onClick={(e) => open(e, `/recordings/${r.id}`)}
                      className="font-semibold text-ink no-underline after:absolute after:inset-0 hover:text-primary-hover"
                    >
                      {r.title}
                    </a>
                    <span className="text-small text-muted">
                      {[mine ? undefined : r.person?.name, r.unit_id ? units.get(r.unit_id) : undefined]
                        .filter(Boolean)
                        .join(", ")}
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
                        : `${staffWord(r.type, labels)} ${Math.round(share * 100)}% of speech, others ${100 - Math.round(share * 100)}%`
                    }
                    {...(share === null ? {} : { caption: `${staffWord(r.type, labels)} ${Math.round(share * 100)}%` })}
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
