import { useId } from "react";

import { cx } from "./cx";

export type ProgressTone = "primary" | "success" | "danger";

// Upload.dc.html:260-264: uploading primary, ready success-bar, error danger-bar.
const fills: Record<ProgressTone, string> = {
  primary: "bg-primary",
  success: "bg-success-bar",
  danger: "bg-danger-bar",
};

export interface ProgressBarProps {
  value: number;
  max?: number;
  /** Accessible name, for example "Uploading Front desk, morning shift.mp3". */
  label: string;
  /** Show the label and value above the bar instead of only announcing them. */
  showLabel?: boolean;
  /** Human-readable value, for example "38.4 of 100 hours". Defaults to a percentage. */
  valueText?: string;
  tone?: ProgressTone;
  className?: string;
}

/** 6px bar on a track (Main.dc.html:72, Upload.dc.html:118). The fill animates only without reduced motion. */
export function ProgressBar({
  value,
  max = 100,
  label,
  showLabel = false,
  valueText,
  tone = "primary",
  className,
}: ProgressBarProps) {
  const labelId = useId();
  const clamped = Math.min(Math.max(value, 0), max);
  const percent = max > 0 ? (clamped / max) * 100 : 0;
  const text = valueText ?? `${Math.round(percent)}%`;
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      {showLabel && (
        <div className="flex justify-between gap-2 text-sm">
          <span id={labelId} className="text-muted">
            {label}
          </span>
          <span className="font-semibold tabular-nums">{text}</span>
        </div>
      )}
      <div
        role="progressbar"
        aria-label={showLabel ? undefined : label}
        aria-labelledby={showLabel ? labelId : undefined}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={clamped}
        aria-valuetext={text}
        className="h-1.5 overflow-hidden rounded-full bg-track"
      >
        <div
          className={cx(
            "h-full rounded-full motion-safe:transition-[width] motion-safe:duration-300 motion-safe:ease-out",
            fills[tone],
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
