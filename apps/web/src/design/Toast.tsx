import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { cx } from "./cx";
import { ToastContext, type ToastApi, type ToastOptions, type ToastTone } from "./toastContext";

// Not in the designs. A white card with a tone stripe; tones follow the upload rows (Upload.dc.html:260-264).
const stripes: Record<ToastTone, string> = {
  info: "border-l-primary",
  success: "border-l-success-bar",
  error: "border-l-danger-bar",
};

export interface ToastProps {
  tone?: ToastTone;
  title: ReactNode;
  message?: ReactNode;
  requestId?: string;
  /** Text before the request id. */
  requestIdLabel?: string;
  onDismiss?: () => void;
  dismissLabel?: string;
  className?: string;
}

/**
 * One toast card. It has no live-region role itself: render it through ToastProvider (useToast), whose
 * regions announce it, or inside your own role="status" / role="alert" container.
 */
export function Toast({
  tone = "info",
  title,
  message,
  requestId,
  requestIdLabel = "Request ID",
  onDismiss,
  dismissLabel = "Dismiss notification",
  className,
}: ToastProps) {
  return (
    <div
      className={cx(
        "flex items-start gap-3 rounded-card border border-l-4 border-line bg-surface py-3 pl-4 pr-1 text-ink motion-safe:animate-toast-in",
        stripes[tone],
        className,
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1 py-0.5">
        <p className="m-0 font-semibold">{title}</p>
        {message && <p className="m-0 text-sm text-ink-2">{message}</p>}
        {requestId && (
          <p className="m-0 text-caption text-muted">
            {requestIdLabel}: <span className="select-all font-semibold tabular-nums text-ink-2">{requestId}</span>
          </p>
        )}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={dismissLabel}
          className="flex min-h-touch min-w-touch shrink-0 items-center justify-center rounded text-muted hover:bg-surface-subtle hover:text-ink"
        >
          <svg
            aria-hidden="true"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      )}
    </div>
  );
}

interface ToastEntry extends ToastOptions {
  id: string;
}

const DEFAULT_DURATION = 6000;

export interface ToastProviderProps {
  children: ReactNode;
  /** Accessible label for each toast's dismiss button. */
  dismissLabel?: string;
  requestIdLabel?: string;
}

/**
 * Holds the toasts and two always-present live regions in the bottom-right corner: role="status" (polite) for
 * info and success, role="alert" (assertive) for errors. Regions exist before any toast so they are announced.
 */
export function ToastProvider({ children, dismissLabel, requestIdLabel }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const nextId = useRef(0);

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (options: ToastOptions) => {
      nextId.current += 1;
      const id = `toast-${nextId.current}`;
      const tone = options.tone ?? "info";
      setToasts((all) => [...all, { ...options, tone, id }]);
      const duration = options.duration ?? (tone === "error" ? undefined : DEFAULT_DURATION);
      if (duration !== undefined)
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), duration),
        );
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => clearTimeout(timer));
  }, []);

  const api = useMemo<ToastApi>(() => ({ show, dismiss }), [show, dismiss]);
  const render = (t: ToastEntry) => (
    <Toast
      key={t.id}
      tone={t.tone}
      title={t.title}
      message={t.message}
      requestId={t.requestId}
      requestIdLabel={requestIdLabel}
      dismissLabel={dismissLabel}
      onDismiss={() => dismiss(t.id)}
    />
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col gap-2 sm:left-auto sm:w-[380px]">
        <div role="status" aria-live="polite" className="pointer-events-auto flex flex-col gap-2">
          {toasts.filter((t) => t.tone !== "error").map(render)}
        </div>
        <div role="alert" aria-live="assertive" className="pointer-events-auto flex flex-col gap-2">
          {toasts.filter((t) => t.tone === "error").map(render)}
        </div>
      </div>
    </ToastContext.Provider>
  );
}
