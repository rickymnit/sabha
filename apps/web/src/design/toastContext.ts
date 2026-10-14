import { createContext, useContext, type ReactNode } from "react";

export type ToastTone = "info" | "success" | "error";

export interface ToastOptions {
  tone?: ToastTone;
  title: ReactNode;
  message?: ReactNode;
  /** The API's problem+json `request_id`, shown so staff can quote it to support. */
  requestId?: string;
  /** Milliseconds before the toast closes itself. Errors stay until dismissed unless this is set. */
  duration?: number;
}

export interface ToastApi {
  /** Shows a toast and returns its id. */
  show: (options: ToastOptions) => string;
  dismiss: (id: string) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

/** Shows and dismisses toasts. Needs a <ToastProvider> above it. */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used inside <ToastProvider>");
  return api;
}
