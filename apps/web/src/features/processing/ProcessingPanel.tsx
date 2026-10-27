// How a recording went through the pipeline, for owners and admins (P7.8): each stage's runs with their timing and
// errors in plain words, and the AI cost Sabha recorded (never an estimate, golden rule 6).

import type { ProcessingInfo } from "../../api/types";
import { formatDateTime } from "../../app/format";
import { Panel, cx } from "../../design";
import { STAGE_NAMES } from "./stages";

function seconds(ms: number | null): string {
  if (ms === null) return "";
  const s = Math.round(ms / 1000);
  return s < 90 ? `${s} s` : `${Math.round(s / 60)} min`;
}

export function ProcessingPanel({ info }: { info: ProcessingInfo }) {
  const cost = info.ai.cost_usd;
  return (
    <Panel title="Processing details" description="Visible to owners and administrators only.">
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
                  run.status === "succeeded" ? "bg-success" : run.status === "failed" ? "bg-danger" : "bg-primary",
                )}
              />
              <span className="font-semibold">{STAGE_NAMES[run.stage] ?? run.stage}</span>
              <span className="text-muted">
                {run.attempt > 1 ? `attempt ${run.attempt}, ` : ""}
                {run.status === "running" ? "running" : run.status === "succeeded" ? "done" : "failed"}
                {run.duration_ms !== null ? ` in ${seconds(run.duration_ms)}` : ""}, {formatDateTime(run.started_at)}
              </span>
              {run.error && <span className="basis-full pl-5 text-danger">{run.error}</span>}
            </li>
          ))}
        </ol>
      )}
      <p className="mb-0 mt-4 text-sm text-muted">
        {info.ai.calls === 0
          ? "No AI calls yet."
          : `AI: ${info.ai.calls} ${info.ai.calls === 1 ? "call" : "calls"}${cost !== null ? `, US$${cost.toFixed(4)} recorded` : ""}${info.ai.unpriced_calls ? ` (${info.ai.unpriced_calls} without a published price)` : ""}.`}
      </p>
    </Panel>
  );
}
