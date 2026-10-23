// "Measured from the transcript" (Analysis.dc.html:173-185): numbers computed in code (P5.5), each with its
// definition in a tooltip. The tooltip opens on hover and keyboard focus, closes on Escape, and is the label's
// accessible description (aria-describedby), so screen readers hear it without opening it. It is positioned
// `fixed` under the label so the panel's rounded, clipped corners never cut it off; scrolling closes it.

import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";

import { formatMetricValue, formatRange } from "./format";
import type { Metric } from "./types";

export interface ReportMetricsProps {
  metrics: readonly Metric[];
  /** Seek the audio, for metrics that point at a stretch of the recording. */
  onSeek: (ms: number) => void;
}

const TOOLTIP_PX = 280;
const EDGE_PX = 8;

function MetricCell({ metric, onSeek }: { metric: Metric; onSeek: (ms: number) => void }) {
  const tooltipId = useId();
  const labelRef = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<CSSProperties | null>(null);
  const open = position !== null;

  const show = () => {
    const box = labelRef.current?.getBoundingClientRect();
    const viewport = document.documentElement.clientWidth || window.innerWidth;
    const width = Math.min(TOOLTIP_PX, viewport - 2 * EDGE_PX);
    const left = Math.max(EDGE_PX, Math.min(box?.left ?? 0, viewport - width - EDGE_PX));
    setPosition({ top: (box?.bottom ?? 0) + 6, left, width });
  };
  const hide = useCallback(() => setPosition(null), []);

  useEffect(() => {
    if (!open) return;
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [open, hide]);

  const value = formatMetricValue(metric);
  const median = metric.median ? formatMetricValue({ value: metric.median.value, unit: metric.unit }) : null;

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && open) {
      event.stopPropagation();
      hide();
    }
  };

  return (
    <div
      className="relative flex flex-col gap-0.5 border-l border-t border-track px-5 py-3.5"
      data-metric={metric.key}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <dt className="text-small text-muted">
        <button
          ref={labelRef}
          type="button"
          aria-describedby={tooltipId}
          onFocus={show}
          onBlur={hide}
          onKeyDown={onKeyDown}
          className="cursor-help text-left underline decoration-muted-2 decoration-dotted underline-offset-4"
        >
          {metric.name}
        </button>
      </dt>
      <span
        role="tooltip"
        id={tooltipId}
        hidden={!open}
        style={position ?? undefined}
        className="fixed z-20 rounded border border-line bg-ink px-3 py-2 text-caption text-surface shadow-[0_4px_12px_rgba(23,33,29,0.18)]"
      >
        {metric.definition}
      </span>
      <dd className="m-0 text-2xl font-semibold">
        {value ?? (
          <>
            <span aria-hidden="true">—</span>
            <span className="sr-only">Not measured</span>
          </>
        )}
      </dd>
      {metric.detail && <dd className="m-0 text-caption text-muted">{metric.detail}</dd>}
      {metric.range && (
        <dd className="m-0 text-caption text-muted">
          <button
            type="button"
            onClick={() => onSeek((metric.range as { start_ms: number }).start_ms)}
            className="text-primary hover:text-primary-hover hover:underline"
          >
            <span className="sr-only">Play from </span>
            {formatRange(metric.range)}
          </button>
        </dd>
      )}
      {metric.median && median && (
        <dd className="m-0 text-caption text-muted">
          {metric.median.scope} median {median}
        </dd>
      )}
    </div>
  );
}

// Full class names so Tailwind can see them.
const WIDE_COLUMNS: Record<number, string> = {
  1: "lg:grid-cols-1",
  2: "lg:grid-cols-2",
  3: "lg:grid-cols-3",
  4: "lg:grid-cols-4",
  5: "lg:grid-cols-5",
};

/** At most 5 per row on wide screens, in rows as even as possible: 7 metrics -> 4 + 3, not 5 + 2 or 6 + 1. */
function metricLayout(count: number): { columns: number; pad: number } {
  if (count === 0) return { columns: 1, pad: 0 };
  const rows = Math.ceil(count / 5);
  const columns = Math.ceil(count / rows);
  return { columns, pad: rows * columns - count };
}

export function ReportMetrics({ metrics, onSeek }: ReportMetricsProps) {
  const headingId = useId();
  const layout = metricLayout(metrics.length);
  return (
    <section aria-labelledby={headingId} className="rounded-panel border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-5 py-3.5">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          Measured from the transcript
        </h2>
        <span className="text-small text-muted">Counted directly, not judged by AI</span>
      </div>
      {/* Dividers on every cell's top and left edge; the outer ones sit outside this wrapper and are clipped. */}
      <div className="overflow-hidden rounded-b-panel border-t border-line-subtle">
        <dl className={`-ml-px -mt-px mb-0 grid grid-cols-2 ${WIDE_COLUMNS[layout.columns]}`}>
          {metrics.map((metric) => (
            <MetricCell key={metric.key} metric={metric} onSeek={onSeek} />
          ))}
          {/* Empty cells finish the last row, so no metric sits alone on a row of blank space. */}
          {Array.from({ length: layout.pad }, (_, i) => (
            <div key={`pad-${i}`} aria-hidden="true" className="hidden border-l border-t border-track lg:block" />
          ))}
          {metrics.length % 2 === 1 && <div aria-hidden="true" className="border-l border-t border-track lg:hidden" />}
        </dl>
      </div>
    </section>
  );
}
