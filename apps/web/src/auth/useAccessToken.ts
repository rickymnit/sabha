import { useAuth } from "react-oidc-context";

/** The current access token for `Authorization: Bearer`, or undefined when signed out. */
export function useAccessToken(): string | undefined {
  return useAuth().user?.access_token;
}
