import { cx } from "./cx";
import { scoreBand, type ScoreBand } from "./score";

// UI v2 rubric rows (docs/design/v2/03-lesson-report.png, 04-sales-report.png): five short rounded dashes, 16 x 5px, 4px apart.
const fills: Record<ScoreBand, string> = {
  low: "bg-danger-bar",
  mid: "bg-warning-bar",
  good: "bg-success-bar",
};

export interface ScoreBarProps {
  score: number;
  max?: number;
  /** Value text. Defaults to "{score} of {max}". */
  valueText?: string;
  /** Hides the value text; the segments then carry it as their accessible name. */
  hideValue?: boolean;
  className?: string;
}

/** Five segments, filled up to the (rounded) score in the score's band colour. */
export function ScoreBar({ score, max = 5, valueText, hideValue = false, className }: ScoreBarProps) {
  const filled = Math.max(0, Math.min(max, Math.round(score)));
  const text = valueText ?? `${score} of ${max}`;
  const fill = fills[scoreBand(score)];
  const segments = (
    <span className="flex gap-1">
      {Array.from({ length: max }, (_, i) => (
        <span
          key={i}
          data-filled={i < filled}
          className={cx("h-[5px] w-4 rounded-full", i < filled ? fill : "bg-line")}
        />
      ))}
    </span>
  );

  if (hideValue) {
    return (
      <span role="img" aria-label={text} className={cx("inline-flex", className)}>
        {segments}
      </span>
    );
  }
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <span aria-hidden="true">{segments}</span>
      <span className="font-semibold tabular-nums">{text}</span>
    </span>
  );
}
