// /my: a sales rep's own Overview (founder's Sales Executive dashboard doc, 2026-11-12). One simple first view:
// calls, meetings and all interactions this week or month, one combined quality score with the change from the
// period before, the next actions that matter most, recent calls and meetings, and the overall coaching focus.
// Numbers come from GET /v1/me/summary (computed in code); a score with nothing behind it shows "—", never 0.

import { useState, type ReactNode } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { useMyCoaching, useMyNextActions, useMySummary, useRecordings } from "../../api/hooks";
import type { Me, RecordingItem } from "../../api/types";
import { formatWhen } from "../../app/format";
import { useOpen } from "../../app/useOpen";
import { Button, EmptyState, Icon, Panel, ScoreChip, SegmentedControl, Skeleton, cx } from "../../design";
import { InteractionChip, InterestPill, PriorityPill } from "../../features/workspace/parts";
import { clientOf, dueText, pendingWords } from "../../features/workspace/words";
import { useInterestLabels } from "../../features/workspace/useInterestLabels";

const PERIOD_WORDS = { week: "this week", month: "this month" } as const;
const PREVIOUS_WORDS = { week: "last week", month: "last month" } as const;

function Tile({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-panel border border-line bg-surface px-5 py-4">
      <span className="text-small font-semibold text-muted">{label}</span>
      <span className="text-[28px] font-bold leading-tight tabular-nums text-ink">{value}</span>
      {detail && <span className="text-small text-muted">{detail}</span>}
    </div>
  );
}

function change(now: number, before: number, word: string): string {
  if (now === before) return `Same as ${word}`;
  return `${now > before ? "+" : "−"}${Math.abs(now - before)} vs ${word}`;
}

function LinkOut({ to, children }: { to: string; children: ReactNode }) {
  const open = useOpen();
  return (
    <a href={to} onClick={(e) => open(e, to)} className="text-sm font-semibold no-underline">
      {children}
    </a>
  );
}

export function MyOverviewPage() {
  const me = useOutletContext<Me>();
  const navigate = useNavigate();
  const [period, setPeriod] = useState<"week" | "month">("week");
  const summary = useMySummary(period);
  const actions = useMyNextActions();
  const coaching = useMyCoaching();
  const recent = useRecordings({ type: "sales" }, 5);
  const labels = useInterestLabels();
  const name = me.user.name.split(" ")[0] ?? me.user.name;
  const current = summary.data?.current;
  const previous = summary.data?.previous;
  const rows = recent.data?.pages[0]?.items ?? [];
  const top = (actions.data?.items ?? []).slice(0, 3);
  const focus = coaching.data?.themes.find((t) => t.key === coaching.data?.focus);
  const latestTip = coaching.data?.practice_points[0];

  const scoreDetail =
    current?.score != null && previous?.score != null
      ? `${current.score >= previous.score ? "Up" : "Down"} from ${previous.score.toFixed(1)} ${PREVIOUS_WORDS[period]}`
      : current?.score != null
        ? `From ${current.scored} scored ${current.scored === 1 ? "interaction" : "interactions"}`
        : "No scored interactions yet";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-[26px] font-bold">Hello, {name}</h1>
          <p className="m-0 text-muted">Your calls and meetings, what to do next, and what to work on.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SegmentedControl
            label="Period"
            value={period}
            onChange={setPeriod}
            options={[
              { value: "week", label: "Week" },
              { value: "month", label: "Month" },
            ]}
          />
          <Button onClick={() => navigate("/upload")}>
            <Icon name="upload" size={16} /> Add a recording
          </Button>
        </div>
      </div>

      <section aria-label={`Activity ${PERIOD_WORDS[period]}`} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {summary.isPending || !current || !previous ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px] w-full rounded-panel" />)
        ) : (
          <>
            <Tile
              label="Calls"
              value={current.calls}
              detail={change(current.calls, previous.calls, PREVIOUS_WORDS[period])}
            />
            <Tile
              label="Meetings"
              value={current.meetings}
              detail={change(current.meetings, previous.meetings, PREVIOUS_WORDS[period])}
            />
            <Tile
              label="All interactions"
              value={current.total}
              detail={change(current.total, previous.total, PREVIOUS_WORDS[period])}
            />
            <Tile
              label="Quality score"
              value={current.score == null ? "—" : <ScoreChip score={current.score} variant="text" decimals={1} />}
              detail={scoreDetail}
            />
          </>
        )}
      </section>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)]">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel
            flush
            title="Next actions"
            actions={top.length > 0 && <LinkOut to="/my/actions">All next actions</LinkOut>}
          >
            {actions.isPending ? (
              <div className="p-5">
                <Skeleton className="h-16 w-full" />
              </div>
            ) : top.length === 0 ? (
              <EmptyState
                headingAs="h3"
                title="No follow-ups waiting"
                description="When a client agrees a next step in a call or meeting, it shows here."
              />
            ) : (
              <ul className="m-0 flex list-none flex-col p-0">
                {top.map((a) => (
                  <li key={a.recording_id} className="border-b border-line-subtle last:border-b-0">
                    <button
                      type="button"
                      onClick={() => navigate(`/my/interactions/${a.recording_id}`)}
                      className="flex w-full flex-col gap-1.5 bg-transparent px-5 py-3.5 text-left hover:bg-surface-faint"
                    >
                      <span className="flex flex-wrap items-center gap-2">
                        <PriorityPill priority={a.priority} />
                        {dueText(a) && (
                          <span className={cx("text-small", a.overdue ? "font-semibold text-danger" : "text-muted")}>
                            {dueText(a)}
                          </span>
                        )}
                      </span>
                      <span className="font-semibold text-ink">{a.action}</span>
                      <span className="text-small text-muted">{a.client ?? a.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            flush
            title="Recent calls and meetings"
            actions={rows.length > 0 && <LinkOut to="/my/interactions">All interactions</LinkOut>}
          >
            {recent.isSuccess && rows.length === 0 ? (
              <EmptyState
                headingAs="h3"
                title="No calls or meetings yet"
                description="Upload a call or record a meeting, and Sabha writes the summary and the next steps for you."
                action={<Button onClick={() => navigate("/upload")}>Add a recording</Button>}
              />
            ) : (
              <ul className="m-0 flex list-none flex-col p-0">
                {rows.map((r) => (
                  <RecentRow key={r.id} row={r} labels={labels} onOpen={() => navigate(`/my/interactions/${r.id}`)} />
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <Panel title="Your coaching" description="Private to you." actions={<LinkOut to="/my/coaching">Open</LinkOut>}>
          {coaching.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : !focus && !latestTip ? (
            <p className="m-0 text-muted">Your coaching appears after your first scored call or meeting.</p>
          ) : (
            <div className="flex flex-col gap-4">
              {focus && (
                <div className="flex flex-col gap-1 rounded-card bg-primary-tint-subtle px-4 py-3">
                  <span className="text-small font-semibold text-primary-hover">Focus on</span>
                  <span className="text-lg font-semibold text-ink">{focus.name}</span>
                  {focus.score != null && (
                    <span className="text-small text-muted">Your average: {focus.score.toFixed(1)} out of 5</span>
                  )}
                </div>
              )}
              <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
                {coaching.data?.themes.map((t) => (
                  <li key={t.key} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-ink-2">{t.name}</span>
                    <ScoreChip score={t.score} variant="text" decimals={1} emptyLabel="No score yet" />
                  </li>
                ))}
              </ul>
              {latestTip && (
                <div className="flex flex-col gap-1 border-t border-line-subtle pt-3">
                  <span className="text-small font-semibold text-muted">Practise in your next call</span>
                  <span className="text-ink">{latestTip.text}</span>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function RecentRow({
  row,
  labels,
  onOpen,
}: {
  row: RecordingItem;
  labels?: Record<string, string>;
  onOpen: () => void;
}) {
  const done = row.status === "COMPLETED";
  return (
    <li className="border-b border-line-subtle last:border-b-0">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full flex-wrap items-center gap-x-3 gap-y-1.5 bg-transparent px-5 py-3 text-left hover:bg-surface-faint"
      >
        <InteractionChip kind={row.interaction} />
        <span className="flex min-w-0 flex-[1_1_200px] flex-col">
          <span className="truncate font-semibold text-ink">{clientOf(row) ?? row.title}</span>
          <span className="text-small text-muted">{formatWhen(row.recorded_at ?? row.created_at)}</span>
        </span>
        {done ? (
          <>
            <InterestPill value={row.interest_level} labels={labels} />
            <ScoreChip score={row.overall_score} decimals={1} />
          </>
        ) : (
          <span className="text-small text-muted">{pendingWords(row.status)}</span>
        )}
      </button>
    </li>
  );
}
