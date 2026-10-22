// /login (P6.2). Dev mode: "Sign in as..." the people the local dev sign-in seeded (scripts/admin/dev_seed.py).
// OIDC mode: one button that goes to the identity provider.

import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useDevUsers } from "../api/hooks";
import { ApiError } from "../api/client";
import { Button, Card, EmptyState, PageHeader } from "../design";
import { useSession } from "../session/session";

export function LoginPage() {
  const session = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/recordings";
  const dev = session.mode === "dev";
  const people = useDevUsers(dev && !session.token);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (session.token) return <Navigate to={from} replace />;

  if (!dev) {
    return (
      <div className="mx-auto max-w-md p-8">
        <PageHeader title="Sign in to Sabha" />
        <Button className="mt-6" onClick={() => void session.signInRedirect?.()}>
          Sign in
        </Button>
      </div>
    );
  }

  const signIn = async (subject: string) => {
    setBusy(subject);
    setError(null);
    try {
      await session.signInAs?.(subject);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sign-in failed.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <PageHeader
        title="Sign in (local development)"
        description="This local sign-in works only on a development machine (APP_ENV=local). Pick someone to sign in as."
      />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {people.isPending && <p className="text-sm text-muted">Loading people…</p>}
      {people.isError && (
        <EmptyState
          title="The local sign-in is not available"
          description="Start the API with APP_ENV=local and DEV_LOGIN=true (see .env.example)."
        />
      )}
      {people.data?.length === 0 && (
        <EmptyState title="No one to sign in as yet" description="Run: uv run python scripts/admin/dev_seed.py" />
      )}
      {people.data && people.data.length > 0 && (
        <ul className="flex flex-col gap-2" aria-label="People you can sign in as">
          {people.data.map((person) => (
            <li key={person.subject}>
              <Card className="flex-row items-center justify-between gap-4 p-4">
                <div>
                  <p className="font-semibold text-ink">{person.name}</p>
                  <p className="text-small capitalize text-muted">
                    {person.role} · {person.tenant_name}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  disabled={busy !== null}
                  aria-label={`Sign in as ${person.name}`}
                  onClick={() => void signIn(person.subject)}
                >
                  {busy === person.subject ? "Signing in…" : "Sign in"}
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
