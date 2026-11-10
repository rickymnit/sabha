// /progress: a staff member's own page (a teacher, a sales rep, a support agent; UI v2 style, no mockup of its own).
// How their analysed recordings went in the period, what their newest report says, the rubric points to work on
// next, what is still being processed and their recent recordings. Everything comes from the same APIs as the
// Overview (GET /v1/overview, which counts only their own recordings for staff) and the report; a number whose n is
// 0 is hidden, never shown as 0 (golden rule 6). No comparison with colleagues or the school (owner, 2026-11-10).

import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { useAnalysis, useOverview, useRecording, useRecordings } from "../api/hooks";
import type { Me, RecordingItem } from "../api/types";
import { capitalise, formatWhen } from "../app/format";
import { useOpen } from "../app/useOpen";
import {
  BarSpark,
  Button,
  EmptyState,
  Icon,
  Panel,
  ScoreChip,
  Skeleton,
  SkeletonGroup,
  type ConversationType,
} from "../design";
import { DateRangePicker } from "../features/overview/DateRangePicker";
import { coachingRows, greeting, overviewTiles, type TypeNames } from "../features/overview/metrics";
import { TileRow } from "../features/overview/OverviewPage";
import { Processing, RECENT_SHOWN, Recent } from "../features/overview/panels";
import {
  COMPARE,
  PRESET_WORDS,
  describeRange,
  presetRange,
  toQuery,
  type DayRange,
  type RangePreset,
} from "../features/overview/range";
import type { OverviewStats } from "../features/overview/types";
import type { AnalysisReport, Labels } from "../features/report/types";
import { formatClock } from "../features/transcript/text";

/** The rubric points shown under "What to work on next". */
export const FOCUS_SHOWN = 3;

const TYPES: ConversationType[] = ["teaching", "reception", "counselling", "meeting", "sales", "support"];
const TYPE_NAMES = Object.fromEntries(TYPES.map((t) => [t, capitalise(t)])) as TypeNames;

const isReport = (payload: { status: string } | undefined): payload is AnalysisReport =>
  payload?.status === "completed" || payload?.status === "partial";

export function MyProgressPage({ now }: { now?: () => Date } = {}) {
  const me = useOutletContext<Me>();
  const navigate = useNavigate();
  const today = (now ?? (() => new Date()))();
  // Staff have fewer recordings than a whole school: 30 days shows a fuller picture than 7.
  const [preset, setPreset] = useState<RangePreset>("30d");
  const [range, setRange] = useState<DayRange>(() => presetRange("30d", today));
  const overview = useOverview(toQuery(range));
  const recordings = useRecordings({}, RECENT_SHOWN);
  const labels = me.tenant.labels;
  const things = labels.recording_plural.toLowerCase();
  const stats = overview.data;
  const recent = recordings.data?.pages[0]?.items ?? [];
  const latest = recent.find((r) => r.status === "COMPLETED");

  if (overview.isError) {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name="alert" size={26} />}
          title="We couldn't load your progress"
          description="Please try again in a moment."
          action={<Button onClick={() => void overview.refetch()}>Try again</Button>}
        />
      </Panel>
    );
  }

  const name = me.user.name.split(" ")[0] ?? me.user.name;
  const when = PRESET_WORDS[preset] ?? `, ${describeRange(range)}`;
  const summary = stats
    ? stats.recordings_analysed > 0
      ? `${stats.recordings_analysed} of your ${things} analysed${when}.`
      : `None of your ${things} analysed${when}.`
    : describeRange(range);
  // The top bar has Upload on every page; this one is for the empty state.
  const upload = (
    <Button icon={<Icon name="upload" size={16} />} onClick={() => navigate("/upload")}>
      Upload
    </Button>
  );

  const header = (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="m-0 text-title font-bold text-ink">
          {greeting(today)}, {name}
        </h1>
        <p className="m-0 text-sm text-muted">{summary}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        <DateRangePicker
          preset={preset}
          range={range}
          onChange={(p, r) => {
            setPreset(p);
            setRange(r);
          }}
          now={now}
        />
      </div>
    </header>
  );

  // Nothing uploaded yet: one clear next step instead of empty panels.
  if (recordings.isSuccess && recent.length === 0 && stats && (stats.processing ?? []).length === 0) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        {header}
        <Panel>
          <EmptyState
            className="py-14"
            icon={<Icon name="upload" size={26} />}
            title={`Upload your first ${labels.recording.toLowerCase()}`}
            description="Sabha listens to it, then shows what went well, what to try next and the moments worth playing again."
            action={upload}
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      {header}
      {stats === undefined ? (
        <Skeleton className="h-[118px] rounded-panel" />
      ) : (
        <MyTiles stats={stats} me={me} compare={COMPARE[preset]} />
      )}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
        {latest ? (
          <LatestReport item={latest} labels={labels} />
        ) : (
          <Panel title="Your latest report">
            <p className="m-0 text-sm text-muted">
              {recordings.isPending ? " " : `Your report appears here once one of your ${things} has been analysed.`}
            </p>
          </Panel>
        )}
        <div className="flex min-w-0 flex-col gap-5">
          {stats !== undefined && <Focus stats={stats} labels={labels} />}
          {stats !== undefined && (stats.processing ?? []).length > 0 && (
            <Processing stats={stats} typeNames={TYPE_NAMES} />
          )}
        </div>
      </div>
      <Recent me={me} mine />
    </div>
  );
}

function MyTiles({ stats, me, compare }: { stats: OverviewStats; me: Me; compare: string }) {
  const labels = me.tenant.labels;
  // "Audio processed" is the organisation's running cost, not something a person works on.
  const tiles = overviewTiles(stats, TYPE_NAMES, labels, compare, me.tenant.enabled_types as ConversationType[])
    .filter((t) => t.id !== "audio")
    .map((t) => (t.id.startsWith("median-") ? { ...t, label: `Your ${t.label.charAt(0).toLowerCase()}${t.label.slice(1)}` } : t)); // prettier-ignore
  if (tiles.length === 0) {
    return (
      <Panel title="In this period">
        <p className="m-0 text-sm text-muted">
          None of your {labels.recording_plural.toLowerCase()} were analysed in these dates. Try a longer period.
        </p>
      </Panel>
    );
  }
  return <TileRow tiles={tiles} />;
}

/** The newest analysed recording: the manager's note if it was shared, what went well and what to try next. */
function LatestReport({ item, labels }: { item: RecordingItem; labels: Labels }) {
  const analysis = useAnalysis(item.id);
  const detail = useRecording(item.id);
  const open = useOpen();
  const report = isReport(analysis.data) ? analysis.data : undefined;
  const href = `/recordings/${item.id}`;
  const note = detail.data?.share_note?.trim();
  return (
    <Panel
      title="Your latest report"
      description={`${item.title}, ${formatWhen(item.created_at)}`}
      actions={
        <span className="flex items-center gap-3">
          <ScoreChip score={item.overall_score} decimals={1} />
          <a href={href} onClick={(e) => open(e, href)} className="text-sm font-semibold no-underline">
            Open report
          </a>
        </span>
      }
      className="gap-4"
    >
      {note && (
        <figure className="m-0 flex flex-col gap-1 rounded-card border border-primary-border bg-primary-tint-subtle px-3.5 py-3">
          <figcaption className="text-small font-semibold text-primary-hover">
            Note from {detail.data?.shared_by_name ?? `your ${labels.manager.toLowerCase()}`}
          </figcaption>
          <blockquote className="m-0 whitespace-pre-line text-sm text-ink">{note}</blockquote>
        </figure>
      )}
      {analysis.isPending ? (
        <SkeletonGroup label="Loading the report" className="flex flex-col gap-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-2/3" />
        </SkeletonGroup>
      ) : !report ? (
        <p className="m-0 text-sm text-muted">This report can't be shown here. Open it to see why.</p>
      ) : (
        <>
          {report.summary && <p className="m-0 text-sm text-ink-2">{report.summary}</p>}
          {report.strengths.length > 0 && (
            <section aria-label="What went well" className="flex flex-col gap-1.5">
              <h3 className="m-0 text-sm font-semibold text-ink">What went well</h3>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                {report.strengths.slice(0, 2).map((s) => (
                  <li key={s} className="flex gap-2 text-sm text-ink-2">
                    <span aria-hidden="true" className="mt-1.5 size-1.5 shrink-0 rounded-full bg-success" />
                    {s}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {report.suggestions.length > 0 && (
            <section aria-label="Try next time" className="flex flex-col gap-1.5">
              <h3 className="m-0 text-sm font-semibold text-ink">Try next time</h3>
              <ol className="m-0 flex list-none flex-col gap-2 p-0">
                {report.suggestions.map((s, i) => (
                  <li key={`${i}:${s.utterance_id}`} className="flex gap-2.5 text-sm text-ink-2">
                    <span
                      aria-hidden="true"
                      className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary-tint text-caption font-semibold text-primary-hover"
                    >
                      {i + 1}
                    </span>
                    <span>
                      {s.text}{" "}
                      <span className="whitespace-nowrap text-small text-muted">at {formatClock(s.start_ms)}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          )}
          <p className="m-0 text-small text-muted">
            Every point comes with the moment in the {labels.recording.toLowerCase()} it is based on. Open the report to
            play it.
          </p>
        </>
      )}
    </Panel>
  );
}

/** The person's lowest rubric points in the period, with their weekly trend and a link to how each is scored. */
function Focus({ stats, labels }: { stats: OverviewStats; labels: Labels }) {
  const open = useOpen();
  const rows = coachingRows(stats).slice(0, FOCUS_SHOWN);
  return (
    <Panel title="What to work on next" description="Your lowest rubric points in this period, 1 to 5">
      {rows.length === 0 ? (
        <p className="m-0 text-sm text-muted">Not enough verified scores in this period yet.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {rows.map((item) => {
            const weekly = item.weekly ?? [];
            const known = weekly.flatMap((w) => (w.median === null ? [] : [w.median]));
            const [first, last] = [known[0], known.at(-1)];
            const href = `/rubrics/${encodeURIComponent(item.rubric_id)}`;
            const count = `${item.n} ${(item.n === 1 ? labels.recording : labels.recording_plural).toLowerCase()}`;
            return (
              <li key={`${item.rubric_id}:${item.dimension_key}`} className="flex flex-col gap-1.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-sm font-semibold text-ink">{item.dimension_name}</span>
                    <span className="text-small text-muted">
                      From {count} ·{" "}
                      <a href={href} onClick={(e) => open(e, href)} className="no-underline">
                        How it's scored<span className="sr-only">: {item.dimension_name}</span>
                      </a>
                    </span>
                  </div>
                  <ScoreChip score={item.median} decimals={1} />
                </div>
                {known.length > 1 && (
                  <span className="flex items-center gap-2.5">
                    <BarSpark
                      values={weekly.map((w) => (w.median === null ? null : w.median / 5))}
                      label={`Weekly median: ${weekly.map((w) => (w.median === null ? "none" : w.median.toFixed(1))).join(", ")}`}
                      height={22}
                    />
                    {first !== undefined && last !== undefined && (
                      <span className="whitespace-nowrap text-small tabular-nums text-muted" aria-hidden="true">
                        {weekly.length} weeks: {first.toFixed(1)} → {last.toFixed(1)}
                      </span>
                    )}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
