import type { ReactNode } from "react";

import { cx } from "./cx";

export interface SegmentedOption<Value extends string> {
  value: Value;
  label: ReactNode;
}

export interface SegmentedControlProps<Value extends string> {
  /** Accessible name of the group, for example "Filter by type". */
  label: string;
  options: SegmentedOption<Value>[];
  value: Value;
  onChange: (value: Value) => void;
  className?: string;
}

/**
 * Toggle buttons in a grey track (Main.dc.html:154-160, Plans.dc.html:118-120): role="group" with aria-pressed.
 * Buttons are 44px tall, above the design's 32-36px (tokens.md "Touch size").
 */
export function SegmentedControl<Value extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: SegmentedControlProps<Value>) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cx("inline-flex flex-wrap gap-1 rounded-seg-outer bg-fill p-[3px]", className)}
    >
      {options.map((option) => {
        const pressed = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={pressed}
            onClick={() => onChange(option.value)}
            className={cx(
              "min-h-touch rounded-seg px-3 text-sm",
              pressed ? "bg-surface font-semibold text-ink shadow-seg" : "text-muted hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
