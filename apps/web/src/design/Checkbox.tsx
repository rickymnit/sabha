import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";

import { cx } from "./cx";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "children"> {
  label: ReactNode;
  /** Secondary text under the label, linked with aria-describedby (Upload.dc.html:203-204). */
  description?: ReactNode;
  /** Class names for the wrapping <label>, which is the 44px touch target. */
  className?: string;
}

/** Native checkbox wrapped in its label (Setup.dc.html:71-72, Rubrics.dc.html:169). 18px box, 44px row. */
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, description, className, id, disabled, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const labelId = `${inputId}-label`;
  const descriptionId = `${inputId}-description`;
  return (
    <label
      htmlFor={inputId}
      className={cx(
        "flex min-h-touch gap-2.5 py-1.5",
        description ? "items-start" : "items-center",
        disabled ? "cursor-not-allowed text-muted-2" : "cursor-pointer",
        className,
      )}
    >
      <input
        ref={ref}
        id={inputId}
        type="checkbox"
        disabled={disabled}
        // The whole row is the <label> (a big click target); aria-labelledby keeps the description out of the name.
        aria-labelledby={labelId}
        aria-describedby={description ? descriptionId : undefined}
        className={cx("m-0 h-4.5 w-4.5 shrink-0 accent-primary", description ? "mt-0.5" : undefined)}
        {...rest}
      />
      <span className="flex min-w-0 flex-col gap-0.5">
        <span id={labelId} className="font-semibold">
          {label}
        </span>
        {description && (
          <span id={descriptionId} className="text-small text-muted">
            {description}
          </span>
        )}
      </span>
    </label>
  );
});
