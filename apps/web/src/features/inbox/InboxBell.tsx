// The header bell (UI v2): how many things wait for the signed-in person's decision, and the list in a panel.
// Exactly the "Needs your decision" items (owner's choice, 2026-10-27); nothing is marked read, an item goes when it
// is dealt with.

import { useEffect, useId, useRef, useState } from "react";

import { useInbox } from "../../api/hooks";
import type { Me } from "../../api/types";
import { Icon, cx } from "../../design";
import { InboxList } from "./InboxList";

export function InboxBell({ me }: { me: Me }) {
  const inbox = useInbox();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const box = useRef<HTMLDivElement>(null);
  const items = inbox.data?.items ?? [];
  const n = items.length;

  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={n ? `Needs your decision, ${n} waiting` : "Needs your decision, nothing waiting"}
        onClick={() => setOpen((o) => !o)}
        className="relative flex size-11 items-center justify-center rounded border border-line bg-surface text-ink-2 hover:bg-surface-subtle"
      >
        <Icon name="bell" size={18} />
        {n > 0 && (
          <span
            aria-hidden="true"
            className="absolute -right-1 -top-1 min-w-[18px] rounded-full bg-primary px-1 text-center text-2xs font-semibold leading-[18px] text-surface"
          >
            {n > 99 ? "99+" : n}
          </span>
        )}
      </button>
      <section
        id={panelId}
        aria-label="Needs your decision"
        hidden={!open}
        className={cx(
          "absolute right-0 top-full z-30 mt-1.5 w-[min(420px,calc(100vw-32px))] overflow-hidden rounded-panel border border-line bg-surface shadow-lg",
        )}
      >
        <h2 className="m-0 border-b border-line-subtle px-4 py-3 text-md font-semibold text-ink">
          Needs your decision
        </h2>
        {n > 0 ? (
          <InboxList items={items} me={me} onNavigate={() => setOpen(false)} className="max-h-[60vh] overflow-auto" />
        ) : (
          <p className="m-0 px-4 py-6 text-sm text-muted">
            {inbox.isError ? "We couldn't load this. Please try again in a moment." : "Nothing is waiting for you."}
          </p>
        )}
      </section>
    </div>
  );
}
