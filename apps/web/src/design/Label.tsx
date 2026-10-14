import type { LabelHTMLAttributes } from "react";

import { cx } from "./cx";

export type LabelProps = LabelHTMLAttributes<HTMLLabelElement>;

/** Form label, 13px / 600 (Upload.dc.html:171). Pair it with a control through `htmlFor`. */
export function Label({ className, children, ...rest }: LabelProps) {
  return (
    <label className={cx("text-sm font-semibold text-ink", className)} {...rest}>
      {children}
    </label>
  );
}
