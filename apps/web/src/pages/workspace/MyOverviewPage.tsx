// /my: a sales rep's own Overview (founder's Sales Executive dashboard doc, 2026-11-12), built to read at a glance
// (manager's feedback, 2026-11-12). Top to bottom: three numbers (conversations, quality in words, follow-ups due),
// what to do next, recent conversations by client name, and the one coaching theme to focus on.
// Numbers come from GET /v1/me/summary (computed in code); a score with nothing behind it shows "No score yet".

import { useState, type ReactNode } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { useMyCoaching, useMyNextActions, useMySummary, useRecordings } from "../../api/hooks";
import type { Me } from "../../api/types";
import { useOpen } from "../../app/useOpen";
import { Button, EmptyState, Panel, SegmentedControl, Skeleton, cx, scoreBand, scoreWord } from "../../design";
import { ActionRow } from "../../features/workspace/ActionRow";
import { ConversationRow } from "../../features/workspace/ConversationRow";
import { ScoreVerdict } from "../../features/workspace/parts";
import { useInterestLabels } from "../../features/workspace/useInterestLabels";

const PERIOD_WORDS = { week: "this week", month: "this month" } as const;
const PREVIOUS_WORDS = { week: "last week", month: "last month" } as const;

function Stat({ label, children, detail }: { label: string; children: ReactNode; detail?: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 px-5 py-4">
      <span className="text-small font-semibold text-muted">{label}</span>
      <div className="flex min-h-[34px] items-center">{children}</div>
      {detail && <span className="text-small text-muted">{detail}</span>}
    </div>
  );
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
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
  const allActions = actions.data?.items ?? [];
  const top = allActions.slice(0, 3);
  const overdue = allActions.filter((a) => a.overdue).length;
  const soon = allActions.filter((a) => a.priority !== "low").length;
  const focus = coaching.data?.themes.find((t) => t.key === coaching.data?.focus);
  const latestTip = coaching.data?.practice_points[0];

  const kinds =
    current && current.calls + current.meetings > 0
      ? [
          current.calls && plural(current.calls, "call", "calls"),
          current.meetings && plural(current.meetings, "meeting", "meetings"),
        ]
          .filter(Boolean)
          .join(" · ")
      : null;
  const trend =
    current?.score != null && previous?.score != null
      ? scoreBand(current.score) === scoreBand(previous.score)
        ? `${current.score >= previous.score ? "Up" : "Down"} from ${previous.score.toFixed(1)} ${PREVIOUS_WORDS[period]}`
        : `Was ${scoreWord(previous.score)} ${PREVIOUS_WORDS[period]}`
      : current?.score != null
        ? `From ${plural(current.scored, "scored conversation", "scored conversations")}`
        : null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-[26px] font-bold">Hello, {name}</h1>
          <p className="m-0 text-muted">Here is how your calls and meetings went {PERIOD_WORDS[period]}.</p>
        </div>
        <SegmentedControl
          label="Period"
          value={period}
          onChange={setPeriod}
          options={[
            { value: "week", label: "This week" },
            { value: "month", label: "This month" },
          ]}
        />
      </div>

      <section
        aria-label={`Summary ${PERIOD_WORDS[period]}`}
        className="grid grid-cols-2 divide-line-subtle rounded-panel border border-line bg-surface sm:grid-cols-3 sm:divide-x"
      >
        {summary.isPending || !current || !previous ? (
          [0, 1, 2].map((i) => (
            <div key={i} className={cx("px-5 py-4", i === 2 && "col-span-2 sm:col-span-1")}>
              <Skeleton className="h-[72px] w-full" />
            </div>
          ))
        ) : (
          <>
            <Stat
              label="Conversations"
              detail={
                kinds ??
                `${current.total === previous.total ? "Same as" : current.total > previous.total ? "More than" : "Fewer than"} ${PREVIOUS_WORDS[period]}`
              }
            >
              <span className="text-[28px] font-bold leading-none tabular-nums text-ink">{current.total}</span>
            </Stat>
            <Stat label="Quality" detail={trend}>
              <ScoreVerdict score={current.score} size="lg" />
            </Stat>
            <div className="col-span-2 border-t border-line-subtle sm:col-span-1 sm:border-t-0">
              <Stat
                label="Follow-ups"
                detail={
                  overdue > 0 ? (
                    <span className="font-semibold text-danger">{plural(overdue, "is overdue", "are overdue")}</span>
                  ) : soon > 0 ? (
                    `${soon} to do soon`
                  ) : (
                    "Nothing urgent"
                  )
                }
              >
                <span className="text-[28px] font-bold leading-none tabular-nums text-ink">{allActions.length}</span>
              </Stat>
            </div>
          </>
        )}
      </section>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel
            flush
            title="Do next"
            actions={allActions.length > 3 && <LinkOut to="/my/actions">See all {allActions.length}</LinkOut>}
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
                  <ActionRow
                    key={a.recording_id}
                    item={a}
                    onOpen={() => navigate(`/my/interactions/${a.recording_id}`)}
                  />
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            flush
            title="Recent conversations"
            actions={rows.length > 0 && <LinkOut to="/my/interactions">See all</LinkOut>}
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
                  <ConversationRow
                    key={r.id}
                    row={r}
                    labels={labels}
                    onOpen={() => navigate(`/my/interactions/${r.id}`)}
                  />
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <Panel
          title="Work on next"
          description="Private to you."
          actions={<LinkOut to="/my/coaching">Your coaching</LinkOut>}
        >
          {coaching.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : !focus && !latestTip ? (
            <p className="m-0 text-muted">Your coaching appears after your first scored call or meeting.</p>
          ) : (
            <div className="flex flex-col gap-4">
              {focus && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-lg font-semibold text-ink">{focus.name}</span>
                  <ScoreVerdict score={focus.score} />
                  <span className="text-small text-muted">Your lowest area over the last 30 days.</span>
                </div>
              )}
              {latestTip && (
                <div className="flex flex-col gap-1 rounded-card bg-primary-tint-subtle px-4 py-3">
                  <span className="text-small font-semibold text-primary-hover">Try in your next call</span>
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
