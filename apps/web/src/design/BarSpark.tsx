import { cx } from "./cx";

// Small bar trend (UI v2, docs/design/v2/01-overview.png: the tiles and the coaching table's "Trend, 8 weeks").
// Heights are 0 to 1 of the box; a period without data is a short grey stub, not a zero bar.

export interface BarSparkProps {
  /** One value per period, oldest first, 0 to 1; null where there is no data. */
  values: readonly (number | null)[];
  /** Accessible summary, for example "Lessons analysed per week: 120, 140, 182". */
  label: string;
  /** Box height in px. Default 36 (tiles). */
  height?: number;
  /** Mark the last bar (this period) in the strong colour. */
  highlightLast?: boolean;
  /** Colour of the highlighted bar. */
  tone?: "primary" | "warning";
  className?: string;
}

export function BarSpark({
  values,
  label,
  height = 36,
  highlightLast = true,
  tone = "primary",
  className,
}: BarSparkProps) {
  return (
    <span role="img" aria-label={label} className={cx("inline-flex items-end gap-[3px]", className)} style={{ height }}>
      {values.map((value, i) => {
        const last = highlightLast && i === values.length - 1;
        return (
          <span
            key={i}
            className={cx(
              "w-[5px] rounded-sm",
              value === null
                ? "bg-track"
                : last
                  ? tone === "warning"
                    ? "bg-warning-bar"
                    : "bg-primary"
                  : "bg-primary-tint-strong",
            )}
            style={{ height: value === null ? 3 : Math.max(3, Math.round(value * height)) }}
          />
        );
      })}
    </span>
  );
}
