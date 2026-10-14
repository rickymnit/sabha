import type { ReactNode } from "react";

import { cx } from "./cx";
import { Label } from "./Label";

export interface FieldProps {
  /** Id of the control; the hint and error get `${id}-hint` and `${id}-error`. */
  id: string;
  label: ReactNode;
  /** Keeps the label for screen readers but hides it on screen (for example a search box with an icon). */
  hideLabel?: boolean;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** Label, control, hint and error stacked with a 6px gap (Upload.dc.html:171). Used by Input and Select. */
export function Field({ id, label, hideLabel = false, hint, error, className, children }: FieldProps) {
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id} className={hideLabel ? "sr-only" : undefined}>
        {label}
      </Label>
      {children}
      {hint && (
        <span id={`${id}-hint`} className="text-small text-muted">
          {hint}
        </span>
      )}
      {error && (
        <span id={`${id}-error`} className="text-small font-semibold text-danger">
          {error}
        </span>
      )}
    </div>
  );
}
