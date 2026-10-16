// Sign-in settings for the identity provider (plan task P1.5, docs/adr/0002-auth.md).
// Read from VITE_OIDC_* at build time (apps/web/.env.example). Only standard OIDC is used, so any provider works.

import type { AuthProviderNoUserManagerProps } from "react-oidc-context";

export interface AuthConfig {
  /** The issuer URL, without a trailing slash. */
  authority: string;
  /** Public client id of this single-page app (PKCE, no secret). */
  clientId: string;
  /** The API identifier; access tokens must carry it (the API's OIDC_AUDIENCE). */
  audience: string;
}

type AuthEnv = Partial<Record<"VITE_OIDC_AUTHORITY" | "VITE_OIDC_CLIENT_ID" | "VITE_OIDC_AUDIENCE", string>>;

/** The sign-in settings, or null when any of them is missing. */
export function readAuthConfig(env: AuthEnv): AuthConfig | null {
  const authority = env.VITE_OIDC_AUTHORITY?.trim().replace(/\/+$/, "");
  const clientId = env.VITE_OIDC_CLIENT_ID?.trim();
  const audience = env.VITE_OIDC_AUDIENCE?.trim();
  if (!authority || !clientId || !audience) return null;
  return { authority, clientId, audience };
}

/** Removes the code and state from the address bar once the sign-in callback has been handled. */
export function clearSigninParams(): void {
  window.history.replaceState({}, document.title, window.location.pathname);
}

export function oidcSettings(config: AuthConfig, origin: string): AuthProviderNoUserManagerProps {
  return {
    authority: config.authority,
    client_id: config.clientId,
    redirect_uri: `${origin}/`,
    post_logout_redirect_uri: `${origin}/`,
    // offline_access asks for a refresh token, so tokens renew without a hidden iframe (blocked by third-party
    // cookie rules in most browsers).
    scope: "openid profile email offline_access",
    // Without an audience, Auth0 returns an access token our API cannot validate.
    extraQueryParams: { audience: config.audience },
    automaticSilentRenew: true,
    onSigninCallback: clearSigninParams,
  };
}
