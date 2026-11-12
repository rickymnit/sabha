// /my/coaching: a sales rep's private coaching (founder's Sales Executive dashboard doc, 2026-11-12): their average
// score in each coaching theme over the last 30 days with the change from the 30 before, the theme to focus on, and
// the practice point from each call and meeting, newest first, so they can look back at what they learned. Nobody
// else sees this page's coaching: the API returns it only to the person themselves.

import { useNavigate } from "react-router-dom";

import { useMyCoaching } from "../../api/hooks";
import { formatWhen } from "../../app/format";
import { Button, EmptyState, Panel, PageHeader, Skeleton, cx } from "../../design";
import { ScoreVerdict } from "../../features/workspace/parts";
import { conversationName } from "../../features/workspace/words";

export function MyCoachingPage() {
  const navigate = useNavigate();
  const coaching = useMyCoaching();
  const data = coaching.data;
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Private coaching"
        description="Only you can see this page. Your manager sees your scores, not your coaching."
        actions={
          <Button variant="secondary" onClick={() => navigate("/rubrics")}>
            How you're scored
          </Button>
        }
      />
      {coaching.isPending ? (
        <Panel>
          <Skeleton className="h-32 w-full" />
        </Panel>
      ) : !data || (data.themes.every((t) => t.score == null) && data.practice_points.length === 0) ? (
        <Panel>
          <EmptyState
            title="Your coaching starts with your first call"
            description="After a call or meeting is analysed, your coaching themes and practice points show here."
          />
        </Panel>
      ) : (
        <>
          <Panel title="Your coaching themes" description="Your average over the last 30 days, out of 5.">
            <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2">
              {data.themes.map((t) => {
                const focus = t.key === data.focus;
                const diff = t.score != null && t.previous != null ? t.score - t.previous : null;
                return (
                  <li
                    key={t.key}
                    className={cx(
                      "flex flex-col gap-2 rounded-card border px-4 py-3",
                      focus ? "border-primary-border bg-primary-tint-subtle" : "border-line-subtle",
                    )}
                  >
                    <span className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <span className="font-semibold text-ink">{t.name}</span>
                      <ScoreVerdict score={t.score} />
                    </span>
                    <span className="h-1.5 overflow-hidden rounded-full bg-fill" aria-hidden="true">
                      {t.score != null && (
                        <span
                          className={cx("block h-full rounded-full", focus ? "bg-danger-bar" : "bg-primary")}
                          style={{ width: `${(t.score / 5) * 100}%` }}
                        />
                      )}
                    </span>
                    <span className="text-small text-muted">
                      {focus
                        ? "Work on this first: your lowest area"
                        : t.score == null
                          ? "Not scored in the last 30 days"
                          : diff == null
                            ? `From ${t.count} ${t.count === 1 ? "score" : "scores"}`
                            : diff === 0
                              ? "Same as the 30 days before"
                              : `${diff > 0 ? "Up" : "Down"} ${Math.abs(diff).toFixed(1)} from the 30 days before`}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Panel>

          <Panel
            flush
            title="Practice points"
            description="One thing to practise from each call and meeting, newest first."
          >
            {data.practice_points.length === 0 ? (
              <p className="m-0 px-5 py-4 text-muted">
                Your next analysed call or meeting gives you one thing to practise. It shows here.
              </p>
            ) : (
              <ul className="m-0 flex list-none flex-col p-0">
                {data.practice_points.map((p) => (
                  <li key={p.recording_id} className="border-b border-line-subtle last:border-b-0">
                    <button
                      type="button"
                      onClick={() => navigate(`/my/interactions/${p.recording_id}`)}
                      className="flex w-full flex-col gap-1 bg-transparent px-5 py-3.5 text-left hover:bg-surface-faint"
                    >
                      <span className="text-ink">{p.text}</span>
                      <span className="text-small text-muted">
                        {conversationName(p.client, p.interaction, p.recorded_at)}
                        {p.client ? ` · ${formatWhen(p.recorded_at)}` : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
