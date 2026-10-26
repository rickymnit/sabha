// A modal dialog: labelled by its title, focus moves in on open and back to the trigger on close, Escape closes, and
// Tab stays inside. Mount it only while open (a fresh body each time).

import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface DialogProps {
  title: string;
  description?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

const FOCUSABLE = "select, input, textarea, button:not([disabled]), a[href]";

export function Dialog({ title, description, onClose, children }: DialogProps) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<Element | null>(null);

  useEffect(() => {
    returnFocus.current = document.activeElement;
    ref.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => {
      if (returnFocus.current instanceof HTMLElement) returnFocus.current.focus();
    };
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !ref.current) return;
    const focusable = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        className="flex max-h-full w-full max-w-[520px] flex-col gap-4 overflow-y-auto rounded-panel border border-line bg-surface p-6"
      >
        <h2 id={titleId} className="m-0 text-xl font-semibold">
          {title}
        </h2>
        {description && <div className="m-0 text-sm text-muted">{description}</div>}
        {children}
      </div>
    </div>
  );
}
