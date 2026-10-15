// What the report page shows before or instead of a report: processing, failed and needs review. None of these
// shows a score or a quote.

import { Panel, ProgressBar, StatusChip, cx } from "../../design";
import { formatIst } from "./format";
import type {
  AnalysisFailed,
  AnalysisNeedsReview,
  AnalysisProcessing,
  Labels,
  PipelineStage,
  StatusReason,
} from "./types";

const STAGES: { stage: PipelineStage; label: string }[] = [
  { stage: "uploaded", label: "Uploaded" },
  { stage: "preprocessing", label: "Preparing the audio" },
  { stage: "diarizing", label: "Telling speakers apart" },
  { stage: "transcribing", label: "Transcribing" },
  { stage: "analyzing", label: "Scoring against the rubric" },
];

function Reasons({ reasons }: { reasons: StatusReason[] }) {
  if (reasons.length === 0) return null;
  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0">
      {reasons.map((r, i) => (
        <li key={i} className="text-ink-2">
          {r.message} <span className="text-caption text-muted">({r.code})</span>
        </li>
      ))}
    </ul>
  );
}

/** Live progress placeholder: the stage list and the stage's progress. The real page refreshes this (P6.2+). */
export function ProcessingState({ analysis, labels }: { analysis: AnalysisProcessing; labels: Labels }) {
  const current = STAGES.findIndex((s) => s.stage === analysis.stage);
  const label = STAGES[current]?.label ?? analysis.stage;
  const progress = analysis.progress;
  return (
    <Panel
      title="Analysis in progress"
      description={`The report appears here when this ${labels.recording.toLowerCase()} has been analysed.`}
      actions={<StatusChip status={analysis.stage === "analyzing" ? "analysing" : "transcribing"}>{label}</StatusChip>}
      data-state="processing"
    >
      <ol className="m-0 flex list-none flex-col gap-2 p-0" aria-label="Stages">
        {STAGES.map((s, i) => {
          const state = i < current ? "done" : i === current ? "current" : "waiting";
          return (
            <li
              key={s.stage}
              aria-current={state === "current" ? "step" : undefined}
              className={cx(
                "flex items-center gap-2.5 text-sm",
                state === "done" && "text-success",
                state === "current" && "font-semibold text-ink",
                state === "waiting" && "text-muted",
              )}
            >
              <span
                aria-hidden="true"
                className={cx(
                  "h-2 w-2 rounded-full",
                  state === "done" ? "bg-success-bar" : state === "current" ? "bg-primary" : "bg-line",
                )}
              />
              {s.label}
              <span className="sr-only">
                {state === "done" ? ", done" : state === "current" ? ", in progress" : ""}
              </span>
            </li>
          );
        })}
      </ol>
      {typeof progress === "number" && (
        <ProgressBar
          label={label}
          showLabel
          value={progress * 100}
          valueText={`${Math.round(progress * 100)}%`}
          className="max-w-md"
        />
      )}
      <p className="m-0 text-caption text-muted" aria-live="polite">
        Last update {formatIst(analysis.updated_at)} IST.
      </p>
    </Panel>
  );
}

export function FailedState({ analysis, labels }: { analysis: AnalysisFailed; labels: Labels }) {
  return (
    <Panel title="The analysis could not be completed" data-state="failed">
      <Reasons reasons={analysis.reasons} />
      <p className="m-0 text-ink-2">
        No scores were produced for this {labels.recording.toLowerCase()}. If it happens again, contact your Sabha
        administrator and quote reference{" "}
        <strong className="font-semibold">{analysis.reference ?? analysis.recording_id}</strong>.
      </p>
    </Panel>
  );
}

export function NeedsReviewState({ analysis, labels }: { analysis: AnalysisNeedsReview; labels: Labels }) {
  return (
    <Panel
      title={`This ${labels.recording.toLowerCase()} needs review`}
      actions={<StatusChip status="needs-review" />}
      data-state="needs-review"
    >
      <Reasons reasons={analysis.reasons} />
      <p className="m-0 text-ink-2">Scores stay hidden until a reviewer has checked the analysis.</p>
    </Panel>
  );
}
