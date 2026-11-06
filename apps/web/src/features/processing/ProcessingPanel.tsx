// How a recording went through the pipeline, for owners and admins (P7.8): each stage's runs with their timing and
// errors in plain words, and the AI cost Sabha recorded (never an estimate, golden rule 6).

import type { ProcessingInfo } from "../../api/types";
import { formatDateTime } from "../../app/format";
import { cx } from "../../design";
import { STAGE_NAMES } from "./stages";

function seconds(ms: number | null): string {
  if (ms === null) return "";
  const s = Math.round(ms / 1000);
  return s < 90 ? `${s} s` : `${Math.round(s / 60)} min`;
}

/** The pipeline runs, as a part of TechnicalDetails. */
export function ProcessingPanel({ info }: { info: ProcessingInfo }) {
  const cost = info.ai.cost_usd;
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h3 className="m-0 text-base font-semibold">Processing details</h3>
        <p className="m-0 text-sm text-muted">Visible to owners and administrators only.</p>
      </div>
      {info.stages.length === 0 ? (
        <p className="m-0 text-muted">Nothing has run yet.</p>
      ) : (
        <ol className="m-0 flex list-none flex-col gap-2 p-0 text-sm">
          {info.stages.map((run) => (
            <li key={`${run.stage}-${run.attempt}-${run.started_at}`} className="flex flex-wrap items-baseline gap-x-3">
              <span
                aria-hidden="true"
                className={cx(
                  "h-2 w-2 shrink-0 rounded-full",
                  run.status === "succeeded"
                    ? "bg-success"
                    : run.status === "failed"
                      ? "bg-danger"
                      : run.status === "retrying" || run.status === "needs_review"
                        ? "bg-warning"
                        : "bg-primary",
                )}
              />
              <span className="font-semibold">{STAGE_NAMES[run.stage] ?? run.stage}</span>
              <span className="text-muted">
                {run.attempt > 1 ? `attempt ${run.attempt}, ` : ""}
                {
                  {
                    running: "running",
                    succeeded: "done",
                    failed: "failed",
                    retrying: "did not finish; waiting to try again",
                    needs_review: "stopped for a person to decide",
                  }[run.status]
                }
                {run.duration_ms !== null ? ` in ${seconds(run.duration_ms)}` : ""}, {formatDateTime(run.started_at)}
              </span>
              {run.error && (
                <span className={cx("basis-full pl-5", run.status === "failed" ? "text-danger" : "text-ink-2")}>
                  {run.error}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      <p className="mb-0 mt-4 text-sm text-muted">
        {info.ai.calls === 0
          ? "No AI calls yet."
          : `AI: ${info.ai.calls} ${info.ai.calls === 1 ? "call" : "calls"}${cost !== null ? `, US$${cost.toFixed(4)} recorded` : ""}${info.ai.unpriced_calls ? ` (${info.ai.unpriced_calls} without a published price)` : ""}.`}
      </p>
    </section>
  );
}
