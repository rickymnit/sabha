import type { ReactNode } from "react";

import { cx } from "./cx";

export type MetricFootTone = "success" | "warning" | "danger" | "muted";

export interface Metric {
  /** Stable key for the cell. */
  id: string;
  label: ReactNode;
  value: ReactNode;
  /** Quieter text after the value, for example " / 5" or " h" (Main.dc.html:121). */
  suffix?: ReactNode;
  /** Line under the value: a delta, a note or a link. */
  foot?: ReactNode;
  footTone?: MetricFootTone;
}

const footTones: Record<MetricFootTone, string> = {
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  muted: "text-muted",
};

export interface MetricStripProps {
  /** Accessible name of the strip, for example "This week". */
  label: string;
  metrics: Metric[];
  className?: string;
}

/**
 * The 4-cell headline panel (Main.dc.html:108-127): 13px muted label, 28px / 600 value, 12.5px foot.
 * Cells wrap below 200px each; dividers are drawn on every cell's top and left edge and the outer ones are
 * clipped, so the lines stay correct however the cells wrap.
 */
export function MetricStrip({ label, metrics, className }: MetricStripProps) {
  return (
    <section
      aria-label={label}
      className={cx("overflow-hidden rounded-panel border border-line bg-surface", className)}
    >
      <dl className="-ml-px -mt-px grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
        {metrics.map((m) => (
          <div key={m.id} className="flex flex-col gap-1.5 border-l border-t border-line-subtle px-5 py-4.5">
            <dt className="text-sm text-muted">{m.label}</dt>
            <dd className="m-0 text-metric font-semibold tabular-nums text-ink">
              {m.value}
              {m.suffix && <span className="text-lg font-medium text-muted-2">{m.suffix}</span>}
            </dd>
            {m.foot && <dd className={cx("m-0 text-small", footTones[m.footTone ?? "muted"])}>{m.foot}</dd>}
          </div>
        ))}
      </dl>
    </section>
  );
}
