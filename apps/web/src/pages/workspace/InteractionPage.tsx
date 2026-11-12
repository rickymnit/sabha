// /my/interactions/:id: one call or meeting at a glance for the sales rep (founder's Sales Executive dashboard doc,
// 2026-11-12), so they understand it and the next customer action without listening to the recording first: call
// or meeting, client and date, the quality score, the AI summary, what the client needs and worries about, the
// AI-suggested interest, the next action with its date, and their private coaching for the next call. The full
// report (recording, transcript, every score with its evidence) is one click away. Every item shown is quote-backed
// by the analysis (golden rule 5); a time opens the full report at that moment.

import { useNavigate, useParams } from "react-router-dom";

import { useAnalysis, useMyNextActions, useRecording } from "../../api/hooks";
import { formatDateTime, formatDuration } from "../../app/format";
import { Button, EmptyState, Icon, Panel, Skeleton, cx } from "../../design";
import { NextTimePanel } from "../../features/report/NextTimePanel";
import { TimeChip } from "../../features/report/SalesPanels";
import type { AnalysisReport } from "../../features/report/types";
import { InterestPill, KindLabel, PriorityPill, ScoreVerdict } from "../../features/workspace/parts";
import { conversationName, dueText, pendingWords, plainAction } from "../../features/workspace/words";
import { useInterestLabels } from "../../features/workspace/useInterestLabels";

const OWNER = { sales_rep: "Your step", customer: "Waiting on the client", both: "You and the client" } as const;

const isReport = (payload: { status: string } | undefined): payload is AnalysisReport =>
  payload?.status === "completed" || payload?.status === "partial";

export function InteractionPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const recording = useRecording(id);
  const analysis = useAnalysis(id);
  const labels = useInterestLabels();
  const actions = useMyNextActions();
  const full = (ms?: number) => navigate(`/recordings/${id}${ms === undefined ? "" : `?at=${ms}`}`);

  if (recording.isError) {
    return (
      <Panel>
        <EmptyState
          headingAs="h1"
          icon={<Icon name="alert" size={26} />}
          title="We couldn't find this call or meeting"
          action={<Button onClick={() => navigate("/my/interactions")}>Back to my interactions</Button>}
        />
      </Panel>
    );
  }
  if (recording.isPending) {
    return (
      <Panel>
        <Skeleton className="h-40 w-full" />
      </Panel>
    );
  }
  const detail = recording.data;
  const report = isReport(analysis.data) ? analysis.data : undefined;
  const card = report?.deal_card ?? null;
  const client = detail.client_name || card?.client_name?.name || null;
  const step = card?.next_step ?? null;
  const planned = actions.data?.items.find((a) => a.recording_id === id); // the date worked out in code
  const due = planned ? dueText(planned) : step?.due ? `When: “${step.due}”` : null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3">
        <a
          href="/my/interactions"
          onClick={(e) => {
            e.preventDefault();
            navigate("/my/interactions");
          }}
          className="inline-flex items-center gap-1 text-sm font-semibold no-underline"
        >
          <Icon name="arrowLeft" size={16} /> My interactions
        </a>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1.5">
            <h1 className="m-0 text-[26px] font-bold leading-tight">
              {conversationName(client, detail.interaction, detail.recorded_at)}
            </h1>
            <span className="flex flex-wrap items-center gap-x-1.5 text-small text-muted">
              {client && <KindLabel kind={detail.interaction} />}
              <span>
                {client ? "· " : ""}
                {formatDateTime(detail.recorded_at)}
              </span>
              {detail.duration_ms ? <span>· {formatDuration(detail.duration_ms)}</span> : null}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            {report && (
              <div className="flex flex-col gap-0.5">
                <span className="text-small font-semibold text-muted">Quality</span>
                <ScoreVerdict score={report.overall} size="lg" />
              </div>
            )}
            <Button variant="secondary" onClick={() => full()}>
              Recording and transcript
            </Button>
          </div>
        </div>
      </div>

      {!report ? (
        <Panel>
          <EmptyState
            title={pendingWords(detail.status)}
            description={
              detail.status === "FAILED" || detail.status === "NEEDS_REVIEW"
                ? (detail.status_note ?? "Open the full report for details.")
                : `Sabha is writing the summary and next steps. This page fills in by itself.`
            }
          />
        </Panel>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]">
          <div className="flex min-w-0 flex-col gap-5">
            <Panel title="What happened">
              <p className="m-0 max-w-[72ch] text-ink-2">{report.summary}</p>
              {card && (card.customer_needs.length > 0 || card.objections.length > 0) && (
                <div className="mt-4 grid gap-4 border-t border-line-subtle pt-4 sm:grid-cols-2">
                  {card.customer_needs.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <span className="text-small font-semibold text-muted">What the client needs</span>
                      <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm text-ink">
                        {card.customer_needs.map((n) => (
                          <li key={n.evidence.utterance_id + n.need}>{n.need}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {card.objections.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <span className="text-small font-semibold text-muted">Concerns raised</span>
                      <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm text-ink">
                        {card.objections.map((o) => (
                          <li key={o.evidence.utterance_id + o.objection}>
                            {o.objection}
                            <span className="text-muted">
                              {o.settled === "yes" ? " · handled" : o.settled === "no" ? " · still open" : ""}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </Panel>
            {report.next_time && <NextTimePanel coaching={report.next_time} onSeek={(ms) => full(ms)} />}
          </div>

          <div className="flex min-w-0 flex-col gap-5">
            <Panel title="Next action">
              {step ? (
                <div className="flex flex-col gap-2">
                  {(planned || due) && (
                    <span className="flex flex-wrap items-center gap-2">
                      {planned && <PriorityPill priority={planned.priority} />}
                      <span className={cx("text-small", planned?.overdue ? "font-semibold text-danger" : "text-ink-2")}>
                        {due ?? "No date agreed"}
                      </span>
                    </span>
                  )}
                  <span className="font-semibold text-ink">{plainAction(step.action)}</span>
                  <span className="text-small text-muted">{OWNER[step.owner]}</span>
                  <span className="flex items-center gap-2 text-small text-muted">
                    <TimeChip ms={step.evidence.start_ms} onSeek={(ms) => full(ms)} />
                    <span>“{step.evidence.quote}”</span>
                  </span>
                </div>
              ) : (
                <p className="m-0 text-muted">No next step was agreed in this {detail.interaction ?? "meeting"}.</p>
              )}
            </Panel>
            <Panel title="Client interest" description="Suggested by Sabha from what the client said.">
              {card?.interest_level ? (
                <div className="flex flex-col gap-2">
                  <InterestPill value={card.interest_level.value} labels={labels} />
                  {card.interest_level.evidence && (
                    <span className="flex items-center gap-2 text-small text-muted">
                      <TimeChip ms={card.interest_level.evidence.start_ms} onSeek={(ms) => full(ms)} />
                      <span>“{card.interest_level.evidence.quote}”</span>
                    </span>
                  )}
                </div>
              ) : (
                <p className="m-0 text-muted">Not clear from this conversation.</p>
              )}
            </Panel>
            {report.next_time && (
              <p className="m-0 text-small text-muted">Your coaching on this page is private to you.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
