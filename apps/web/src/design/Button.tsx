import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  /** Decorative icon shown before the text; it is hidden from assistive technology. */
  icon?: ReactNode;
  fullWidth?: boolean;
}

// Main.dc.html:97 (secondary), :101 (primary); Rubrics.dc.html:98 (disabled primary).
const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-primary px-4 font-semibold text-surface hover:bg-primary-hover disabled:bg-primary-disabled disabled:text-primary-disabled-ink",
  secondary:
    "border border-line-input bg-surface px-3.5 text-ink hover:bg-surface-subtle disabled:bg-surface-subtle disabled:text-muted-2",
  ghost: "px-3 font-semibold text-primary hover:bg-primary-tint-subtle hover:text-primary-hover disabled:text-muted-2",
};

/** A native <button> (type="button" unless set), at least 44px tall. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", icon, fullWidth = false, type = "button", className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(
        "inline-flex min-h-touch min-w-touch items-center justify-center gap-2 rounded text-base disabled:cursor-not-allowed",
        variants[variant],
        fullWidth && "w-full",
        className,
      )}
      {...rest}
    >
      {icon && (
        <span aria-hidden="true" className="flex shrink-0">
          {icon}
        </span>
      )}
      {children}
    </button>
  );
});
