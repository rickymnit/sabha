import type { ReactNode } from "react";

import { cx } from "./cx";

export interface SkeletonProps {
  /** Size and shape, for example "h-4 w-40" or "h-8 w-8 rounded-full". */
  className?: string;
}

/**
 * Grey placeholder block, hidden from assistive technology. It shimmers only when the person has not asked
 * for reduced motion; otherwise it is a flat track-grey block.
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "block h-4 rounded bg-track motion-safe:animate-shimmer motion-safe:bg-gradient-to-r motion-safe:from-track motion-safe:via-surface-subtle motion-safe:to-track motion-safe:bg-[length:200%_100%]",
        className,
      )}
    />
  );
}

export interface SkeletonGroupProps {
  /** What is loading, read by screen readers, for example "Loading recordings". */
  label: string;
  children: ReactNode;
  className?: string;
}

/** Container for skeletons: aria-busy, with the loading text for screen readers. */
export function SkeletonGroup({ label, children, className }: SkeletonGroupProps) {
  return (
    <div aria-busy="true" className={className}>
      <span role="status" className="sr-only">
        {label}
      </span>
      {children}
    </div>
  );
}
