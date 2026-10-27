import { cx } from "./cx";
import { scoreBand, type ScoreBand } from "./score";

// Score chips, UI v2 (docs/design/v2/01- to 04-*.png): tinted box, number in the band's tone.
const chipTones: Record<ScoreBand, string> = {
  low: "bg-danger-tint text-danger",
  mid: "bg-warning-tint text-warning",
  good: "bg-success-tint text-success",
};

// Coloured number without a background, for dense tables.
const textTones: Record<ScoreBand, string> = {
  low: "text-danger",
  mid: "text-warning",
  good: "text-success",
};

export interface ScoreChipProps {
  /** Score from 1 to 5, or null when there is no score yet. */
  score: number | null;
  max?: number;
  /** "chip" has a tinted background (report page); "text" is just the coloured number (overview table). */
  variant?: "chip" | "text";
  /** Decimal places. Defaults to 0 for whole numbers and 1 otherwise. */
  decimals?: number;
  /** Screen-reader text after the number. Defaults to "out of {max}". */
  outOfLabel?: string;
  /** Screen-reader text shown with the "—" when there is no score. */
  emptyLabel?: string;
  className?: string;
}

/** A 1–5 score coloured by band (scoreBand): below 3.0 danger, 3.0 to 3.7 warning, 3.8 and above success. */
export function ScoreChip({
  score,
  max = 5,
  variant = "chip",
  decimals,
  outOfLabel,
  emptyLabel = "No score",
  className,
}: ScoreChipProps) {
  if (score === null) {
    return (
      <span className={cx("font-semibold text-muted-2", className)}>
        <span aria-hidden="true">—</span>
        <span className="sr-only">{emptyLabel}</span>
      </span>
    );
  }
  const band = scoreBand(score);
  const places = decimals ?? (Number.isInteger(score) ? 0 : 1);
  return (
    <span
      data-band={band}
      className={cx(
        "tabular-nums",
        variant === "chip"
          ? cx("inline-block min-w-[34px] rounded-md px-1.5 py-[3px] text-center font-semibold", chipTones[band])
          : cx("font-semibold", textTones[band]),
        className,
      )}
    >
      {score.toFixed(places)}
      <span className="sr-only"> {outOfLabel ?? `out of ${max}`}</span>
    </span>
  );
}
