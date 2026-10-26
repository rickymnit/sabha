// /login. A brand panel (what Sabha does, in three true statements) beside the sign-in card.
// Dev mode: choose one of the demo accounts the local sign-in seeded (scripts/admin/dev_seed.py).
// OIDC mode: one button that goes to the identity provider.

import { useState, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useDevUsers } from "../api/hooks";
import { ApiError } from "../api/client";
import type { DevUser } from "../api/types";
import { Avatar, Button, Icon, Logo, Skeleton, SkeletonGroup } from "../design";
import { useSession } from "../session/session";

// Demo accounts in the order someone showing Sabha would pick them: the head of the school first.
const ROLE_ORDER: DevUser["role"][] = ["owner", "manager", "reviewer", "staff", "admin"];

const POINTS = [
  "Speaker-labelled transcripts in Hindi, English and Hinglish",
  "Every score backed by quotes you can play back",
  "Recordings and results stay in India",
];

function BrandPanel() {
  return (
    <section
      aria-label="About Sabha"
      className="relative hidden flex-col justify-between overflow-hidden bg-primary p-12 text-surface lg:flex lg:w-[44%]"
    >
      <span className="inline-flex items-center gap-2.5">
        <span className="inline-flex h-[34px] w-[34px] items-center justify-center rounded bg-surface">
          <Logo size={26} wordmark={false} />
        </span>
        <span className="text-xl font-bold">Sabha</span>
      </span>
      <div className="flex max-w-md flex-col gap-6">
        <h2 className="m-0 text-[32px] font-bold leading-tight tracking-tight">
          Clear, evidence-backed feedback on every conversation.
        </h2>
        <ul className="m-0 flex list-none flex-col gap-3 p-0 text-md text-primary-tint">
          {POINTS.map((point) => (
            <li key={point} className="flex items-start gap-3">
              <span aria-hidden="true" className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-accent" />
              {point}
            </li>
          ))}
        </ul>
      </div>
      <p className="m-0 text-sm text-primary-border">For schools, colleges and businesses.</p>
      <Waves />
    </section>
  );
}

/** Decorative sound-wave bars along the bottom of the brand panel. */
function Waves() {
  const heights = [18, 34, 52, 30, 64, 44, 22, 58, 38, 70, 26, 48, 60, 32, 20, 46, 66, 36, 54, 24, 40, 62, 28, 50];
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute bottom-24 right-10 flex items-end gap-1.5 opacity-20"
    >
      {heights.map((h, i) => (
        <span key={i} className="w-1.5 rounded-full bg-surface" style={{ height: h }} />
      ))}
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-page">
      <BrandPanel />
      <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
        <div className="flex w-full max-w-[420px] flex-col gap-6">
          <div className="lg:hidden">
            <Logo size={34} />
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

function AccountRow({
  person,
  busy,
  disabled,
  onPick,
}: {
  person: DevUser;
  busy: boolean;
  disabled: boolean;
  onPick: () => void;
}) {
  // prettier-ignore
  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={`Sign in as ${person.name}`}
      onClick={onPick}
      className="flex min-h-[60px] w-full items-center gap-3 rounded-card border border-line-subtle bg-surface px-3.5 py-2.5 text-left hover:border-primary-border hover:bg-primary-tint-subtle disabled:cursor-not-allowed disabled:opacity-60"
    >
      <Avatar name={person.name} size={36} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-semibold text-ink">{person.name}</span>
        <span className="truncate text-small text-muted">{person.title ?? person.tenant_name}</span>
      </span>
      {busy ? (
        <span className="text-small text-muted">Signing in…</span>
      ) : (
        <Icon name="chevronRight" className="text-muted-2" />
      )}
    </button>
  );
}

export function LoginPage() {
  const session = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const dev = session.mode === "dev";
  const people = useDevUsers(dev && !session.token);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (session.token) return <Navigate to={from} replace />;

  if (!dev) {
    return (
      <Shell>
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-title font-bold">Sign in to Sabha</h1>
          <p className="m-0 text-muted">Use your work account.</p>
        </div>
        <Button fullWidth onClick={() => void session.signInRedirect?.()}>
          Continue
        </Button>
      </Shell>
    );
  }

  const signIn = async (subject: string) => {
    setBusy(subject);
    setError(null);
    try {
      await session.signInAs?.(subject);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sign-in failed. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  // One group per organisation (a school, a company), each with its head first.
  const groups = new Map<string, DevUser[]>();
  for (const person of [...(people.data ?? [])].sort(
    (a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role),
  )) {
    groups.set(person.tenant_name, [...(groups.get(person.tenant_name) ?? []), person]);
  }
  return (
    <Shell>
      <div className="flex flex-col gap-1">
        <h1 className="m-0 text-title font-bold">Welcome</h1>
        <p className="m-0 text-muted">Choose an account to explore Sabha.</p>
      </div>
      {error && (
        <p role="alert" className="m-0 rounded border border-danger-tint bg-danger-tint px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      {people.isPending && (
        <SkeletonGroup label="Loading accounts" className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[60px] w-full" />
          ))}
        </SkeletonGroup>
      )}
      {people.isError && (
        <div className="flex flex-col gap-3 rounded-panel border border-line bg-surface p-5">
          <p className="m-0 font-semibold">Sign-in isn't available right now</p>
          <p className="m-0 text-sm text-muted">Check that the Sabha server is running, then try again.</p>
          <Button variant="secondary" className="self-start" onClick={() => void people.refetch()}>
            Try again
          </Button>
        </div>
      )}
      {people.data?.length === 0 && (
        <p className="m-0 rounded-panel border border-line bg-surface p-5 text-muted">
          There are no demo accounts yet. Run the demo set-up first.
        </p>
      )}
      {people.data && people.data.length > 0 && (
        <div className="flex flex-col gap-5">
          {[...groups].map(([organisation, accounts]) => (
            <section key={organisation} aria-label={organisation} className="flex flex-col gap-2">
              <h2 className="m-0 text-small font-semibold uppercase tracking-wide text-muted-2">{organisation}</h2>
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {accounts.map((person) => (
                  <li key={person.subject}>
                    <AccountRow
                      person={person}
                      busy={busy === person.subject}
                      disabled={busy !== null}
                      onPick={() => void signIn(person.subject)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      <p className="m-0 text-caption text-muted-2">Demo accounts for trying Sabha.</p>
    </Shell>
  );
}
