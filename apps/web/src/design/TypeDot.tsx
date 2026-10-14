import type { ReactNode } from "react";

import { cx } from "./cx";
import type { ConversationType } from "./types";

// Full class names so Tailwind can see them. Colours: tokens.md "Conversation types".
const swatches: Record<ConversationType, string> = {
  teaching: "bg-type-teaching",
  reception: "bg-type-reception",
  counselling: "bg-type-counselling",
  meeting: "bg-type-meeting",
  sales: "bg-type-sales",
};

export interface TypeDotProps {
  type: ConversationType;
  /** The type's display name from the tenant's labels. Without it the dot is decorative only. */
  label?: ReactNode;
  className?: string;
}

/** 8px square marker in the type colour, radius 2px (Main.dc.html:64, :183), with an optional label. */
export function TypeDot({ type, label, className }: TypeDotProps) {
  const dot = <span aria-hidden="true" className={cx("h-2 w-2 shrink-0 rounded-xs", swatches[type])} />;
  if (label === undefined) return <span className={cx("inline-flex", className)}>{dot}</span>;
  return (
    <span className={cx("inline-flex items-center gap-1.5", className)}>
      {dot}
      {label}
    </span>
  );
}
