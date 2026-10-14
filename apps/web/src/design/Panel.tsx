import { useId, type HTMLAttributes, type ReactNode } from "react";

import { cx } from "./cx";

type SectionTag = "section" | "div" | "aside" | "article";
type HeadingTag = "h2" | "h3";

export interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  as?: SectionTag;
  /** Panel heading; when set, the panel is labelled by it. Without it, pass `aria-label` if the panel is a landmark. */
  title?: ReactNode;
  headingAs?: HeadingTag;
  description?: ReactNode;
  /** Controls on the right of the heading (a segmented control, buttons). */
  actions?: ReactNode;
  /**
   * Flush panels put the heading in a bar with a divider and leave the body unpadded, for tables and lists
   * (Main.dc.html:150-151). Otherwise the whole panel is padded 18px 20px (Main.dc.html:131).
   */
  flush?: boolean;
  /** Footer bar under a flush panel's body ("Showing 7 of 214", Main.dc.html:196-197). */
  footer?: ReactNode;
}

/** White panel: 1px line border, 12px radius (Main.dc.html:108, :131). */
export function Panel({
  as: Tag = "section",
  title,
  headingAs: Heading = "h2",
  description,
  actions,
  flush = false,
  footer,
  className,
  children,
  ...rest
}: PanelProps) {
  const headingId = useId();
  const header = (title || actions) && (
    <div
      className={cx(
        "flex flex-wrap items-center justify-between gap-3",
        flush && "border-b border-line-subtle px-5 py-4",
      )}
    >
      {title && (
        <div className="flex flex-col gap-1">
          <Heading id={headingId} className="m-0 text-lg font-semibold">
            {title}
          </Heading>
          {description && <p className="m-0 text-sm text-muted">{description}</p>}
        </div>
      )}
      {actions}
    </div>
  );

  return (
    <Tag
      aria-labelledby={title ? headingId : undefined}
      className={cx(
        "rounded-panel border border-line bg-surface",
        flush ? "min-w-0 overflow-hidden" : "flex min-w-0 flex-col gap-3.5 px-5 py-4.5",
        className,
      )}
      {...rest}
    >
      {header}
      {children}
      {flush && footer && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm text-muted">{footer}</div>
      )}
    </Tag>
  );
}

export type CardTone = "plain" | "neutral" | "active" | "warning";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  as?: SectionTag | "li";
  tone?: CardTone;
}

// Stage cards, Main.dc.html:254-258.
const cardTones: Record<CardTone, string> = {
  plain: "border-line-subtle bg-surface",
  neutral: "border-line-subtle bg-surface-subtle",
  active: "border-primary-tint-strong bg-primary-tint-subtle",
  warning: "border-warning-border bg-warning-surface",
};

/** Smaller card inside a panel: 10px radius, 12px 14px padding (Main.dc.html:138, :254). */
export function Card({ as: Tag = "div", tone = "plain", className, children, ...rest }: CardProps) {
  return (
    <Tag className={cx("flex flex-col gap-2 rounded-card border px-3.5 py-3", cardTones[tone], className)} {...rest}>
      {children}
    </Tag>
  );
}
