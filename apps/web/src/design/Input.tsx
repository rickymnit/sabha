import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";

import { cx } from "./cx";
import { Field } from "./Field";
import { describedBy } from "./fieldIds";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "children"> {
  label: ReactNode;
  hideLabel?: boolean;
  hint?: ReactNode;
  error?: ReactNode;
  /** Decorative icon inside the field, before the text (Main.dc.html:92, the header search). */
  leadingIcon?: ReactNode;
  /** Class names for the outer field wrapper (width, margins). */
  className?: string;
}

const box = "min-h-touch rounded border bg-surface text-ink";

/** Text input with its label, optional hint and error (Setup.dc.html:64). 44px tall. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    label,
    hideLabel,
    hint,
    error,
    leadingIcon,
    className,
    id,
    type = "text",
    "aria-describedby": extraDescribedBy,
    ...rest
  },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const border = error ? "border-danger" : "border-line-input";
  const control = (
    <input
      ref={ref}
      id={inputId}
      type={type}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy(inputId, hint, error, extraDescribedBy)}
      {...rest}
      className={cx(
        "w-full min-w-0 placeholder:text-muted-2 disabled:cursor-not-allowed disabled:text-muted-2",
        leadingIcon
          ? "min-h-touch border-0 bg-transparent text-ink focus-visible:outline-none"
          : cx(box, border, "px-3"),
      )}
    />
  );

  return (
    <Field id={inputId} label={label} hideLabel={hideLabel} hint={hint} error={error} className={className}>
      {leadingIcon ? (
        // The ring moves to the wrapper because the borderless input sits inside it.
        <div
          className={cx(
            box,
            border,
            "flex items-center gap-2 px-3 text-muted-2 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary",
          )}
        >
          <span aria-hidden="true" className="flex shrink-0">
            {leadingIcon}
          </span>
          {control}
        </div>
      ) : (
        control
      )}
    </Field>
  );
});
