// The web app (P6.2): session, toasts, data and routes. API errors from any query show a toast with the problem's
// request id; a 401 signs the person out (their session ended).

import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { ApiError } from "../api/client";
import { AuthProvider, readAuthConfig } from "../auth";
import { ToastProvider, useToast } from "../design";
import { DevSessionProvider, OidcSessionProvider } from "../session/providers";
import { authMode, useSession, type AuthMode } from "../session/session";
import { API_ERROR_EVENT, createQueryClient } from "./queries";
import { routes } from "./routes";

export function ApiErrors() {
  const toast = useToast();
  const { signOut } = useSession();
  useEffect(() => {
    const onError = (event: Event) => {
      const error = (event as CustomEvent<unknown>).detail;
      if (error instanceof ApiError && error.status === 401) return signOut();
      if (error instanceof ApiError && error.status === 404) return; // pages show their own "not found"
      toast.show({
        tone: "error",
        title: error instanceof ApiError ? error.title : "Something went wrong",
        message: error instanceof Error ? error.message : undefined,
        requestId: error instanceof ApiError ? error.requestId : undefined,
      });
    };
    window.addEventListener(API_ERROR_EVENT, onError);
    return () => window.removeEventListener(API_ERROR_EVENT, onError);
  }, [toast, signOut]);
  return null;
}

function WithSession({ mode, children }: { mode: AuthMode; children: ReactNode }) {
  if (mode === "dev") return <DevSessionProvider>{children}</DevSessionProvider>;
  return (
    <AuthProvider config={readAuthConfig(import.meta.env)}>
      <OidcSessionProvider>{children}</OidcSessionProvider>
    </AuthProvider>
  );
}

export function App() {
  const [client] = useState(createQueryClient);
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <WithSession mode={authMode(import.meta.env)}>
      <ToastProvider>
        <ApiErrors />
        <QueryClientProvider client={client}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ToastProvider>
    </WithSession>
  );
}
