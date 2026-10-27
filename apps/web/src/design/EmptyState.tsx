import type { ReactNode } from "react";

import { cx } from "./cx";

export interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  /** Decorative icon in a tinted tile (the upload zone's icon, Upload.dc.html:89). */
  icon?: ReactNode;
  /** A button or link that gets the person started. */
  action?: ReactNode;
  headingAs?: "h1" | "h2" | "h3";
  className?: string;
}

/** Centred message for a list or panel with nothing in it yet. Not in the designs; built from the upload zone. */
export function EmptyState({
  title,
  description,
  icon,
  action,
  headingAs: Heading = "h2",
  className,
}: EmptyStateProps) {
  return (
    <div className={cx("flex flex-col items-center gap-3 px-6 py-10 text-center", className)}>
      {icon && (
        <div
          aria-hidden="true"
          className="flex h-14 w-14 items-center justify-center rounded-panel bg-primary-tint text-primary"
        >
          {icon}
        </div>
      )}
      <Heading className="m-0 text-xl font-semibold text-ink">{title}</Heading>
      {description && <p className="m-0 max-w-[48ch] text-muted">{description}</p>}
      {action && <div className="mt-1 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}
