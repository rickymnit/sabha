import type { AnchorHTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";
import { TypeDot } from "./TypeDot";
import type { ConversationType } from "./types";

export interface NavItemProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
  /** Visible text, from the tenant's labels where it names a thing ("Recordings", "People"). */
  children: ReactNode;
  /** Decorative 18px icon (Main.dc.html:39). */
  icon?: ReactNode;
  /** Shows a conversation-type marker instead of an icon (Main.dc.html:64). */
  type?: ConversationType;
  /** The current page: tinted background and aria-current="page". */
  current?: boolean;
  /** Attention badge, for example the Reviews count (Main.dc.html:51). */
  badge?: number;
  /** Screen-reader text for the badge, for example "7 waiting". Defaults to the number. */
  badgeLabel?: string;
  /** Quiet count on the right, for example recordings per conversation type (Main.dc.html:64). */
  count?: number;
}

/**
 * Sidebar link (Main.dc.html:38-60). Rows are 44px tall, above the design's 40px (nav) and 36px (types),
 * per tokens.md "Touch size".
 */
export function NavItem({
  href,
  children,
  icon,
  type,
  current = false,
  badge,
  badgeLabel,
  count,
  className,
  ...rest
}: NavItemProps) {
  return (
    <a
      href={href}
      aria-current={current ? "page" : undefined}
      className={cx(
        "flex min-h-touch items-center justify-between gap-2.5 rounded px-2.5 no-underline",
        current ? "bg-primary-tint font-semibold text-primary-hover" : "text-ink-2 hover:bg-surface-subtle",
        className,
      )}
      {...rest}
    >
      <span className="flex min-w-0 items-center gap-2.5">
        {icon && (
          <span aria-hidden="true" className="flex shrink-0">
            {icon}
          </span>
        )}
        {type && <TypeDot type={type} />}
        {children}
      </span>
      {badge !== undefined && (
        // 36px = the design's min-width 22px + 7px padding each side, which it renders content-box (tokens.md).
        <span className="min-w-[36px] rounded-full bg-warning-tint px-[7px] py-px text-center text-caption font-semibold tabular-nums text-warning-ink">
          <span aria-hidden="true">{badge}</span>
          <span className="sr-only">, {badgeLabel ?? badge}</span>
        </span>
      )}
      {count !== undefined && (
        <span className="text-caption tabular-nums text-muted-2">
          <span aria-hidden="true">{count}</span>
          <span className="sr-only">, {count}</span>
        </span>
      )}
    </a>
  );
}
