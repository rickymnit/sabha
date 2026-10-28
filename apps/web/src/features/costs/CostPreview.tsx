// The expected cost of one file on the upload page: its length as the browser reads it, then GET /v1/costs/estimate.
// The length goes up to the page (onDuration) so it is sent with the upload, and the same estimate is kept on the
// recording to compare with the actual cost later.

import { useEffect, useState } from "react";

import { useCostEstimate } from "../../api/hooks";
import type { ConversationType } from "../../design";
import { formatInr, measureDuration } from "./money";

const clock = (ms: number) => {
  const s = Math.round(ms / 1000);
  return s >= 3600
    ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`
    : `${Math.floor(s / 60)} min ${s % 60} s`;
};

export function CostPreview({
  file,
  type,
  onDuration,
}: {
  file: File;
  type: ConversationType;
  onDuration: (ms: number | null) => void;
}) {
  const [duration, setDuration] = useState<number | null | undefined>(undefined);
  const estimate = useCostEstimate(type, duration ?? null);

  useEffect(() => {
    let live = true;
    void measureDuration(file).then((ms) => {
      if (!live) return;
      setDuration(ms);
      onDuration(ms);
    });
    return () => {
      live = false;
    };
    // onDuration is a fresh closure each render; the file is what matters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  if (duration === undefined) return <span className="text-small text-muted">Reading the length…</span>;
  if (duration === null) {
    return <span className="text-small text-muted">The length could not be read, so no cost is estimated.</span>;
  }
  const e = estimate.data?.estimate;
  const perMin = estimate.data?.inr_per_minute;
  return (
    <span className="flex flex-col gap-0.5 text-small text-muted" data-testid="cost-preview">
      <span>
        {clock(duration)}
        {e?.total_inr != null && (
          <>
            {" · "}
            <span className="font-semibold text-ink">Expected cost ≈ {formatInr(e.total_inr)}</span>
            {perMin != null && ` (${formatInr(perMin)}/min)`}
          </>
        )}
      </span>
      {e && (
        <span>
          Speech-to-text {e.asr_inr != null ? formatInr(e.asr_inr) : "price not set"}
          {" · "}AI scoring{" "}
          {e.llm_inr != null
            ? `${formatInr(e.llm_inr)} (from ${e.history_n} earlier)`
            : e.history_n === 0
              ? "no history yet"
              : "exchange rate not set"}
        </span>
      )}
    </span>
  );
}
