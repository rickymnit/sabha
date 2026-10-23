import { useId, type ReactNode } from "react";

import { cx } from "./cx";

export interface ChoiceCardOption<Value extends string> {
  value: Value;
  label: ReactNode;
}

export interface ChoiceCardsProps<Value extends string> {
  /** The group's visible label, for example "Conversation type". */
  legend: ReactNode;
  options: ChoiceCardOption<Value>[];
  value: Value;
  onChange: (value: Value) => void;
  disabled?: boolean;
  /** Text under the cards. */
  hint?: ReactNode;
  className?: string;
}

/**
 * One choice from a few, as cards in a two-column grid (Upload.dc.html:160-167, Setup.dc.html:191). Native radio
 * buttons inside a fieldset, so arrow keys and screen readers work as usual; the radio itself is visually hidden.
 */
export function ChoiceCards<Value extends string>({
  legend,
  options,
  value,
  onChange,
  disabled = false,
  hint,
  className,
}: ChoiceCardsProps<Value>) {
  const name = useId();
  return (
    <fieldset className={cx("m-0 flex min-w-0 flex-col gap-2 border-0 p-0", className)} disabled={disabled}>
      <legend className="mb-2 p-0 text-sm font-semibold text-ink">{legend}</legend>
      <div className="grid grid-cols-2 gap-2">
        {options.map((option) => {
          const checked = option.value === value;
          return (
            <label
              key={option.value}
              className={cx(
                "flex min-h-touch cursor-pointer items-center rounded border px-3 text-table has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
                checked
                  ? "border-primary-border bg-primary-tint-subtle font-semibold text-primary-hover"
                  : "border-line-input bg-surface text-ink hover:bg-surface-subtle",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={checked}
                onChange={() => onChange(option.value)}
                className="sr-only"
              />
              {option.label}
            </label>
          );
        })}
      </div>
      {hint && <p className="m-0 text-small text-muted">{hint}</p>}
    </fieldset>
  );
}
