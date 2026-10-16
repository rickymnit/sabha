import { useEffect, useRef, type ReactNode } from "react";
import { hasAuthParams, useAuth } from "react-oidc-context";

import { Button, EmptyState } from "../design";

/**
 * Shows `children` only to a signed-in person; everyone else is sent to the provider's sign-in page once.
 * Whether they may see a given tenant's data is the API's decision (403 `not_invited` or `forbidden`).
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const redirected = useRef(false);

  const needsSignIn =
    !auth.isAuthenticated && !auth.isLoading && !auth.activeNavigator && !auth.error && !hasAuthParams();

  useEffect(() => {
    if (needsSignIn && !redirected.current) {
      redirected.current = true;
      void auth.signinRedirect();
    }
  }, [needsSignIn, auth]);

  if (auth.error) {
    return (
      <EmptyState
        title="We could not sign you in"
        description="Your session may have ended. Try signing in again."
        action={<Button onClick={() => void auth.signinRedirect()}>Sign in again</Button>}
      />
    );
  }
  if (auth.isAuthenticated) return <>{children}</>;
  return (
    <p role="status" className="m-0 p-10 text-center text-muted">
      Signing you in…
    </p>
  );
}

/** Ends the session with the provider and returns to the start page. P6.2 places it in the app shell. */
export function SignOutButton() {
  const auth = useAuth();
  return (
    <Button variant="ghost" onClick={() => void auth.signoutRedirect()}>
      Sign out
    </Button>
  );
}
