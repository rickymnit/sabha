// Cost and pipeline details of one recording, closed by default: most readers never need them, and they name AI
// models and price sources that mean nothing to a school or a business. Shown only when there is something in it.

import { useRecordingCost } from "../../api/hooks";
import type { ProcessingInfo } from "../../api/types";
import { CostCard } from "../costs/CostCard";
import { Icon } from "../../design";
import { ProcessingPanel } from "./ProcessingPanel";

export function TechnicalDetails({
  recordingId,
  processing,
  models,
}: {
  recordingId: string;
  /** Owners and administrators only. */
  processing?: ProcessingInfo;
  /** AI models that scored the shown analysis; owners and administrators only. */
  models?: readonly string[];
}) {
  const cost = useRecordingCost(recordingId);
  if (!cost.data && !processing) return null;
  return (
    <details className="group rounded-panel border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-panel px-5 py-4 [&::-webkit-details-marker]:hidden">
        <span className="flex flex-col gap-1">
          <span className="text-lg font-semibold">Technical details</span>
          <span className="text-sm text-muted">Cost and processing steps, for support questions.</span>
        </span>
        <Icon name="chevronDown" size={20} className="shrink-0 text-muted transition-transform group-open:rotate-180" />
      </summary>
      <div className="flex flex-col gap-6 border-t border-line-subtle px-5 py-4.5">
        {cost.data && <CostCard cost={cost.data} />}
        {processing && <ProcessingPanel info={processing} />}
        {models && models.length > 0 && <p className="m-0 text-sm text-muted">Scored by {models.join(", ")}.</p>}
      </div>
    </details>
  );
}
