import { cx } from "./cx";
import { initials } from "./initials";

// Logo mark, UI v2 (docs/design/v2/*.png): five rounded sound-wave bars in the two speaker
// colours, staff blue and the other speakers' amber. Heights and widths are for a 30px mark.
const BARS = [
  { height: 12, accent: false },
  { height: 22, accent: false },
  { height: 16, accent: true },
  { height: 20, accent: false },
  { height: 10, accent: true },
];

export interface LogoProps {
  /** Mark height in px; the bars scale with it. Default 30 (the sidebar). */
  size?: number;
  /** Show the "Sabha" word next to the mark. */
  wordmark?: boolean;
  className?: string;
}

/** The Sabha logo. Its accessible name is "Sabha", from the word or, without it, from a label on the mark. */
export function Logo({ size = 30, wordmark = true, className }: LogoProps) {
  const scale = size / 30;
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <span
        role={wordmark ? undefined : "img"}
        aria-label={wordmark ? undefined : "Sabha"}
        aria-hidden={wordmark ? true : undefined}
        className="inline-flex shrink-0 items-center"
        style={{ height: size, gap: 3 * scale }}
      >
        {BARS.map((bar, i) => (
          <span
            key={i}
            className={cx("rounded-full", bar.accent ? "bg-speaker-other" : "bg-speaker-staff")}
            style={{ width: 4 * scale, height: bar.height * scale }}
          />
        ))}
      </span>
      {wordmark && <span className="text-brand font-bold text-ink">Sabha</span>}
    </span>
  );
}

export interface AvatarProps {
  name: string;
  /** Diameter in px. Default 32. */
  size?: number;
  /** "tint" (default): blue initials on a blue tint, for people in lists. "ink": white on ink, the signed-in person. */
  tone?: "tint" | "ink";
  className?: string;
}

/** Initials in a circle. Decorative: the name is always written next to it. */
export function Avatar({ name, size = 32, tone = "tint", className }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        tone === "ink" ? "bg-ink text-surface" : "bg-primary-tint text-primary-hover",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
    >
      {initials(name)}
    </span>
  );
}
