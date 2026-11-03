// The session providers (see ./session.ts): local dev sign-in, OIDC, and a fixed one for tests.

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "react-oidc-context";

import { apiFetch } from "../api/client";
import type { OrganisationPick } from "../api/types";
import { DEV_TOKEN_KEY, SessionContext, type Session } from "./session";

function readStoredToken(): string | undefined {
  try {
    return sessionStorage.getItem(DEV_TOKEN_KEY) ?? undefined;
  } catch {
    return undefined; // storage blocked: the person signs in again
  }
}

/** The API's local sign-in: "dev" (pick a seeded person) or "password" (LOGIN_USERNAME in the API's .env). */
export function DevSessionProvider({ mode = "dev", children }: { mode?: "dev" | "password"; children: ReactNode }) {
  const [token, setToken] = useState<string | undefined>(readStoredToken);
  const keep = useCallback((accessToken: string) => {
    try {
      sessionStorage.setItem(DEV_TOKEN_KEY, accessToken);
    } catch {
      // keep it in memory only
    }
    setToken(accessToken);
  }, []);
  const signInAs = useCallback(
    async (subject: string) => {
      const answer = await apiFetch<{ access_token: string }>("/dev-idp/token", { method: "POST", body: { subject } });
      keep(answer.access_token);
    },
    [keep],
  );
  const signInWithPassword = useCallback(
    async (username: string, password: string) => {
      const answer = await apiFetch<{ access_token: string | null } & Partial<OrganisationPick>>("/auth/login", {
        method: "POST",
        body: { username, password },
      });
      if (answer.access_token) {
        keep(answer.access_token);
        return null;
      }
      return { ticket: answer.ticket ?? "", organisations: answer.organisations ?? [] };
    },
    [keep],
  );
  const chooseOrganisation = useCallback(
    async (ticket: string, tenantId: string) => {
      const answer = await apiFetch<{ access_token: string }>("/auth/organisation", {
        method: "POST",
        body: { ticket, tenant_id: tenantId },
      });
      keep(answer.access_token);
    },
    [keep],
  );
  const signOut = useCallback(() => {
    try {
      sessionStorage.removeItem(DEV_TOKEN_KEY);
    } catch {
      // nothing stored
    }
    setToken(undefined);
  }, []);
  const value = useMemo<Session>(
    () =>
      mode === "password"
        ? { mode, token, ready: true, signInWithPassword, chooseOrganisation, signOut }
        : { mode, token, ready: true, signInAs, signOut },
    [mode, token, signInAs, signInWithPassword, chooseOrganisation, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/** Needs react-oidc-context's AuthProvider above it (src/auth). */
export function OidcSessionProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const value = useMemo<Session>(
    () => ({
      mode: "oidc",
      token: auth.user?.access_token,
      ready: !auth.isLoading,
      signInRedirect: () => auth.signinRedirect(),
      signOut: () => void auth.signoutRedirect(),
    }),
    [auth],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/** For tests and stories: a fixed session. */
export function StaticSessionProvider({ session, children }: { session: Session; children: ReactNode }) {
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}
