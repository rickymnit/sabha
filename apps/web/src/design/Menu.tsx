import { useEffect, useId, useRef, useState } from "react";

import { cx } from "./cx";

export interface MenuItem {
  label: string;
  onSelect: () => void;
  /** Red text, for destructive items. */
  danger?: boolean;
}

/** A "…" button that opens a short list of actions (UI v2 report header). Escape or a click outside closes it. */
export function Menu({ label, items, className }: { label: string; items: MenuItem[]; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  if (items.length === 0) return null;
  return (
    <div ref={box} className={cx("relative", className)}>
      <button
        type="button"
        aria-label={label}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded border border-line-input bg-surface text-lg leading-none text-ink hover:bg-surface-subtle"
      >
        <span aria-hidden="true">⋯</span>
      </button>
      {open && (
        <ul
          id={id}
          className="absolute left-0 z-30 m-0 mt-1 min-w-[220px] list-none rounded-card border border-line bg-surface p-1 shadow-[0_8px_24px_rgba(23,33,29,0.14)]"
        >
          {items.map((item) => (
            <li key={item.label}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
                className={cx(
                  "flex min-h-[40px] w-full items-center rounded px-3 text-left text-sm hover:bg-surface-subtle",
                  item.danger ? "text-danger" : "text-ink",
                )}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
