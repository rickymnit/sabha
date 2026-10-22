// The app shell (P6.2, docs/design/01-overview.png sidebar): logo, tenant, navigation in the tenant's own words,
// the conversation types it has switched on, and the signed-in person. On phones the sidebar stacks above the
// content. Every noun comes from GET /v1/me labels (CLAUDE.md: never hard-code "Teacher" or "Lesson").

import type { MouseEvent, ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useMe } from "../api/hooks";
import type { Me } from "../api/types";
import { Button, EmptyState, NavItem, Skeleton, SkeletonGroup } from "../design";
import { useSession } from "../session/session";
import { capitalise } from "./format";

/** A sidebar link that changes page without reloading (keeps cmd/ctrl-click for a new tab). */
function Link({
  to,
  current,
  children,
  ...rest
}: { to: string; current: boolean; children: ReactNode } & Omit<
  Parameters<typeof NavItem>[0],
  "href" | "children" | "current"
>) {
  // prettier-ignore
  const navigate = useNavigate();
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(to);
  };
  return (
    <NavItem href={to} current={current} onClick={onClick} {...rest}>
      {children}
    </NavItem>
  );
}

export function Sidebar({ me }: { me: Me }) {
  const { pathname } = useLocation();
  const { signOut } = useSession();
  const labels = me.tenant.labels;
  const at = (path: string) => (path === "/" ? pathname === "/" : pathname.startsWith(path));
  return (
    <nav
      aria-label="Main"
      className="flex flex-col gap-6 border-b border-line-subtle bg-surface p-4 md:min-h-screen md:w-64 md:border-b-0 md:border-r"
    >
      <div>
        <p className="text-lg font-bold text-ink">Sabha</p>
        <p className="text-small text-muted">{me.tenant.name}</p>
      </div>
      <div className="flex flex-col gap-1">
        <Link to="/recordings" current={at("/recordings")}>
          {capitalise(labels.recording_plural)}
        </Link>
        <Link to="/upload" current={at("/upload")}>
          Upload
        </Link>
        <Link to="/people" current={at("/people")}>
          {capitalise(labels.person_plural)}
        </Link>
        <Link to="/reviews" current={at("/reviews")}>
          Reviews
        </Link>
        <Link to="/rubrics" current={at("/rubrics")}>
          Rubrics
        </Link>
        <Link to="/settings" current={at("/settings")}>
          Settings
        </Link>
      </div>
      {me.tenant.enabled_types.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="px-2.5 text-caption font-semibold uppercase tracking-wide text-muted-2">Types</p>
          {me.tenant.enabled_types.map((type) => (
            <NavItem key={type} href={`/recordings?type=${type}`} type={type}>
              {capitalise(type)}
            </NavItem>
          ))}
        </div>
      )}
      <div className="mt-auto flex flex-col gap-2 border-t border-line-subtle pt-4">
        <p className="text-sm font-semibold text-ink">{me.user.name}</p>
        <p className="text-small capitalize text-muted">{me.user.role}</p>
        <Button variant="secondary" onClick={signOut}>
          Sign out
        </Button>
      </div>
    </nav>
  );
}

/** Signed-in pages: loads /v1/me once, then the sidebar and the page. */
export function Layout() {
  const me = useMe();
  if (me.isPending) {
    return (
      <div className="p-6">
        <SkeletonGroup label="Loading your workspace" className="flex flex-col gap-3">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-80" />
          <Skeleton className="h-4 w-64" />
        </SkeletonGroup>
      </div>
    );
  }
  if (me.isError) {
    return (
      <EmptyState
        title="Your workspace could not be loaded"
        description={`${me.error.message}${me.error.requestId ? ` (request ${me.error.requestId})` : ""}`}
      />
    );
  }
  return (
    <div className="flex min-h-screen flex-col bg-surface-subtle md:flex-row">
      <Sidebar me={me.data} />
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <Outlet context={me.data} />
      </main>
    </div>
  );
}
