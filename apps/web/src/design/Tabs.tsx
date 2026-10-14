import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { cx } from "./cx";

export interface TabItem<Value extends string> {
  value: Value;
  label: ReactNode;
  panel: ReactNode;
}

export interface TabsProps<Value extends string> {
  /** Accessible name of the tab list. */
  label: string;
  tabs: TabItem<Value>[];
  /** Controlled selected tab. Leave unset (and use defaultValue) for an uncontrolled tab set. */
  value?: Value;
  defaultValue?: Value;
  onChange?: (value: Value) => void;
  className?: string;
}

/**
 * WAI-ARIA tabs: role="tablist", roving tabindex, arrow keys, Home and End; panels are role="tabpanel".
 * Not in the designs; styled from tokens (primary underline on the selected tab, 44px tall).
 */
export function Tabs<Value extends string>({
  label,
  tabs,
  value,
  defaultValue,
  onChange,
  className,
}: TabsProps<Value>) {
  const baseId = useId();
  const [internal, setInternal] = useState<Value | undefined>(defaultValue ?? tabs[0]?.value);
  const selected = value ?? internal;
  const refs = useRef(new Map<Value, HTMLButtonElement>());

  const select = (next: Value) => {
    if (value === undefined) setInternal(next);
    onChange?.(next);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = tabs.length - 1;
    const target = {
      ArrowRight: index === last ? 0 : index + 1,
      ArrowLeft: index === 0 ? last : index - 1,
      Home: 0,
      End: last,
    }[event.key];
    const next = target === undefined ? undefined : tabs[target];
    if (!next) return;
    event.preventDefault();
    select(next.value);
    refs.current.get(next.value)?.focus();
  };

  return (
    <div className={cx("flex flex-col gap-4", className)}>
      <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-line-subtle">
        {tabs.map((tab, index) => {
          const isSelected = tab.value === selected;
          return (
            <button
              key={tab.value}
              ref={(el) => {
                if (el) refs.current.set(tab.value, el);
                else refs.current.delete(tab.value);
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.value}`}
              aria-selected={isSelected}
              aria-controls={`${baseId}-panel-${tab.value}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => select(tab.value)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={cx(
                "-mb-px min-h-touch border-b-2 px-3 text-sm",
                isSelected
                  ? "border-primary font-semibold text-ink"
                  : "border-transparent text-muted hover:border-line-input hover:text-ink",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.value}
          role="tabpanel"
          id={`${baseId}-panel-${tab.value}`}
          aria-labelledby={`${baseId}-tab-${tab.value}`}
          hidden={tab.value !== selected}
          tabIndex={0}
        >
          {tab.value === selected && tab.panel}
        </div>
      ))}
    </div>
  );
}
