import { cx } from "./cx";
import { scoreBand, type ScoreBand } from "./score";

// Report score chips, Analysis.dc.html:196 and :274-278.
const chipTones: Record<ScoreBand, string> = {
  low: "bg-danger-tint text-danger",
  mid: "bg-warning-tint-subtle text-warning",
  good: "bg-success-tint text-success",
};

// Coloured number without a background, as in the overview table (Main.dc.html:233-239).
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

/** A 1–5 score coloured by band: below 3 danger, 3 to 3.99 warning, 4 and above success. */
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
          ? cx("inline-block min-w-[34px] rounded-seg py-[3px] text-center font-bold", chipTones[band])
          : cx("font-semibold", textTones[band]),
        className,
      )}
    >
      {score.toFixed(places)}
      <span className="sr-only"> {outOfLabel ?? `out of ${max}`}</span>
    </span>
  );
}
