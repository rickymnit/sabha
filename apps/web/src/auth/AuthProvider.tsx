import type { ReactNode } from "react";
import { AuthProvider as OidcAuthProvider } from "react-oidc-context";

import { EmptyState } from "../design";
import { oidcSettings, type AuthConfig } from "./config";

export interface AuthProviderProps {
  /** From readAuthConfig; null when the VITE_OIDC_* settings are missing. */
  config: AuthConfig | null;
  children: ReactNode;
}

/** Signs people in with the identity provider (PKCE) and keeps their tokens fresh. */
export function AuthProvider({ config, children }: AuthProviderProps) {
  if (!config) {
    return (
      <EmptyState
        title="Sign-in is not set up"
        description="Set VITE_OIDC_AUTHORITY, VITE_OIDC_CLIENT_ID and VITE_OIDC_AUDIENCE, then rebuild. See docs/setup/auth.md."
      />
    );
  }
  return <OidcAuthProvider {...oidcSettings(config, window.location.origin)}>{children}</OidcAuthProvider>;
}
