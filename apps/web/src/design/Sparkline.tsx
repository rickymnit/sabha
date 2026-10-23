import { cx } from "./cx";
import { scoreBand } from "./score";

const strokes = { low: "stroke-danger-bar", mid: "stroke-type-reception", good: "stroke-success-bar" } as const;
const dots = { low: "fill-danger-bar", mid: "fill-type-reception", good: "fill-success-bar" } as const;

export interface SparklineProps {
  /** Scores from 1 to 5, oldest first. */
  scores: readonly number[];
  /** Accessible name, for example "Last 6 lessons: 2.5 to 3.4, latest 3.4". */
  label: string;
  width?: number;
  height?: number;
  className?: string;
}

/**
 * A small trend line on the fixed 1-5 scale (not stretched to the data, so a flat line means flat scores). The
 * line is neutral; only the latest point takes its score band's colour. Fewer than two scores: just that point.
 */
export function Sparkline({ scores, label, width = 96, height = 28, className }: SparklineProps) {
  const pad = 3;
  const x = (i: number) => (scores.length < 2 ? width / 2 : pad + (i * (width - 2 * pad)) / (scores.length - 1));
  const y = (score: number) => pad + ((5 - Math.min(5, Math.max(1, score))) * (height - 2 * pad)) / 4;
  const last = scores.at(-1);
  if (last === undefined) return null;
  const band = scoreBand(last);
  const points = scores.map((s, i) => `${x(i).toFixed(1)},${y(s).toFixed(1)}`).join(" ");
  return (
    <svg role="img" aria-label={label} width={width} height={height} className={cx("overflow-visible", className)}>
      <line x1={pad} x2={width - pad} y1={y(3)} y2={y(3)} className="stroke-track" strokeWidth={1} />
      {scores.length > 1 && (
        <polyline points={points} fill="none" className="stroke-muted-2" strokeWidth={1.5} strokeLinejoin="round" />
      )}
      <circle cx={x(scores.length - 1)} cy={y(last)} r={3} className={cx(dots[band], strokes[band])} />
    </svg>
  );
}
