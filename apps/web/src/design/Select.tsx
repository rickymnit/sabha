import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";

import { cx } from "./cx";
import { Field } from "./Field";
import { describedBy } from "./fieldIds";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: ReactNode;
  hideLabel?: boolean;
  hint?: ReactNode;
  error?: ReactNode;
  /** Class names for the outer field wrapper. */
  className?: string;
  /** <option> elements. */
  children: ReactNode;
}

/** Native <select> with its label (Upload.dc.html:171-178). 44px tall. */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hideLabel, hint, error, className, id, children, "aria-describedby": extraDescribedBy, ...rest },
  ref,
) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <Field id={selectId} label={label} hideLabel={hideLabel} hint={hint} error={error} className={className}>
      <select
        ref={ref}
        id={selectId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(selectId, hint, error, extraDescribedBy)}
        {...rest}
        className={cx(
          "min-h-touch w-full rounded border bg-surface px-2.5 text-ink disabled:cursor-not-allowed disabled:text-muted-2",
          error ? "border-danger" : "border-line-input",
        )}
      >
        {children}
      </select>
    </Field>
  );
});
