import { cx } from "./cx";
import { initials } from "./initials";

// Logo mark: four bars of a sound wave on the primary square, one in the amber accent (Main.dc.html:22-27).
const BARS = [
  { height: 8, accent: false },
  { height: 16, accent: false },
  { height: 11, accent: true },
  { height: 6, accent: false },
];

export interface LogoProps {
  /** Mark size in px; the bars scale with it. Default 30 (the sidebar). */
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
        className="inline-flex shrink-0 items-center justify-center rounded bg-primary"
        style={{ width: size, height: size, gap: 2 * scale }}
      >
        {BARS.map((bar, i) => (
          <span
            key={i}
            className={cx("rounded-xs", bar.accent ? "bg-brand-accent" : "bg-surface")}
            style={{ width: 3 * scale, height: bar.height * scale }}
          />
        ))}
      </span>
      {wordmark && <span className="text-brand font-bold text-ink">Sabha</span>}
    </span>
  );
}

export interface AvatarProps {
  name: string;
  /** Diameter in px. Default 32 (Main.dc.html:84). */
  size?: number;
  className?: string;
}

/** Initials in a tinted circle (Main.dc.html:84). Decorative: the name is always written next to it. */
export function Avatar({ name, size = 32, className }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-primary-tint-strong font-bold text-primary-hover",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
    >
      {initials(name)}
    </span>
  );
}
