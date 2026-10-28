// Who is signed in, independent of how (P6.2). Three ways, chosen at build time by VITE_AUTH_MODE:
//
// - "dev": the API's local dev sign-in (sabha_api.auth.dev_idp, APP_ENV=local only; decided 2026-10-22). The
//   /login page lists the seeded people; the token lives in sessionStorage for this tab.
// - "password": the API's local password sign-in (POST /auth/login, LOGIN_USERNAME in the API's .env; owner's choice,
//   2026-10-28). Same token and storage as "dev"; the /login page asks for a username and password.
// - "oidc" (default): Auth0 through react-oidc-context (P1.5a). Set up last; no page changes when it arrives.
//
// Pages only use useSession(): a token for the API, whether it is ready, and signOut. Providers: ./providers.tsx.

import { createContext, useContext } from "react";

export type AuthMode = "dev" | "password" | "oidc";

export interface Session {
  mode: AuthMode;
  /** The access token for `Authorization: Bearer`, or undefined when signed out. */
  token: string | undefined;
  /** False while the provider is still restoring a session (OIDC only). */
  ready: boolean;
  /** Dev mode: sign in as one of the seeded people. */
  signInAs?: (subject: string) => Promise<void>;
  /** Password mode: sign in with the username and password set in the API's .env. */
  signInWithPassword?: (username: string, password: string) => Promise<void>;
  /** OIDC mode: send the browser to the identity provider. */
  signInRedirect?: () => Promise<void>;
  signOut: () => void;
}

export const SessionContext = createContext<Session | null>(null);

export const DEV_TOKEN_KEY = "sabha.dev_token";

export function authMode(env: { VITE_AUTH_MODE?: string }): AuthMode {
  const mode = env.VITE_AUTH_MODE?.trim().toLowerCase();
  return mode === "dev" || mode === "password" ? mode : "oidc";
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside a session provider");
  return session;
}
