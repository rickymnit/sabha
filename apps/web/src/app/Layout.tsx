// The app shell (docs/design/01-overview.png sidebar): logo, the school, navigation in the tenant's own words, the
// conversation types it has switched on, and the signed-in person. On phones the sidebar becomes a top bar with a
// menu button. Every noun comes from GET /v1/me labels (CLAUDE.md: never hard-code "Teacher" or "Lesson").
// Only finished pages are in the menu (app/nav.ts).

import { useState, type MouseEvent, type ReactNode } from "react";
import { Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useDisputes, useLiveEvents, useMe, useReviews } from "../api/hooks";
import type { Me } from "../api/types";
import { Avatar, Button, EmptyState, Icon, Logo, NavItem, Skeleton, SkeletonGroup } from "../design";
import { useSession } from "../session/session";
import { capitalise, roleTitle, unitNames } from "./format";
import { RESOLVERS, navItems } from "./nav";

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

export function Sidebar({ me, id }: { me: Me; id?: string }) {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const { signOut } = useSession();
  const labels = me.tenant.labels;
  const type = params.get("type");
  const units = unitNames(me);
  const resolver = RESOLVERS.includes(me.user.role);
  const reviews = useReviews(resolver);
  const disputes = useDisputes(resolver);
  const waiting = (reviews.data?.items.length ?? 0) + (disputes.data?.items.filter((d) => !d.raised_by_me).length ?? 0);
  return (
    <nav id={id} aria-label="Main" className="flex h-full flex-col gap-6 px-3.5 py-5">
      <div className="hidden px-2 md:block">
        <Logo />
      </div>
      <div className="rounded border border-line bg-surface-subtle px-2.5 py-2">
        <p className="m-0 text-sm font-semibold text-ink">{me.tenant.name}</p>
        {units && <p className="m-0 text-caption text-muted-2">{units}</p>}
      </div>
      <div className="flex flex-col gap-0.5">
        {navItems(me).map((item) => (
          <Link
            key={item.to}
            to={item.to}
            icon={<Icon name={item.icon} />}
            current={item.match(pathname) && !(item.to === "/recordings" && type)}
            {...(item.to === "/reviews" && waiting > 0 ? { badge: waiting, badgeLabel: `${waiting} waiting` } : {})}
          >
            {item.label}
          </Link>
        ))}
      </div>
      {me.tenant.enabled_types.length > 1 && (
        <div className="flex flex-col gap-0.5">
          <p className="m-0 px-2.5 pb-1.5 text-caption font-semibold text-muted-2">Conversation types</p>
          {me.tenant.enabled_types.map((t) => (
            <Link key={t} to={`/recordings?type=${t}`} type={t} current={pathname === "/recordings" && type === t}>
              {capitalise(t)}
            </Link>
          ))}
        </div>
      )}
      <div className="mt-auto flex items-center gap-2.5 border-t border-line-subtle px-1 pt-3">
        <Avatar name={me.user.name} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-sm font-semibold text-ink">{me.user.name}</span>
          <span className="text-caption leading-snug text-muted-2">{roleTitle(me.user, labels)}</span>
        </div>
        <Button variant="ghost" aria-label="Sign out" title="Sign out" onClick={signOut} className="text-muted-2">
          <Icon name="signOut" />
        </Button>
      </div>
    </nav>
  );
}

/** Signed-in pages: loads /v1/me once, then the sidebar and the page. */
export function Layout() {
  const me = useMe();
  useLiveEvents(me.isSuccess); // lists, reports and queues update as recordings move (P2.6)
  const { signOut } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  // On phones the menu closes once a page is chosen.
  const closeOnLink = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest("a")) setMenuOpen(false);
  };

  if (me.isPending) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-page">
        <Logo size={40} />
        <SkeletonGroup label="Loading your workspace" className="flex w-64 flex-col gap-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </SkeletonGroup>
      </div>
    );
  }
  if (me.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-page p-4">
        <div className="w-full max-w-md rounded-panel border border-line bg-surface">
          <EmptyState
            icon={<Icon name="alert" size={26} />}
            title="We couldn't open your workspace"
            description={
              <>
                Please try again in a moment. If it keeps happening, tell your administrator
                {me.error.requestId ? ` and quote reference ${me.error.requestId}` : ""}.
              </>
            }
            action={
              <>
                <Button onClick={() => void me.refetch()}>Try again</Button>
                <Button variant="secondary" onClick={signOut}>
                  Sign out
                </Button>
              </>
            }
          />
        </div>
      </div>
    );
  }
  return (
    <div className="flex min-h-screen flex-col bg-page md:flex-row">
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface px-4 py-2 md:hidden">
        <Logo size={28} />
        <Button
          variant="ghost"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          aria-controls="main-menu"
          onClick={() => setMenuOpen((open) => !open)}
          className="text-ink"
        >
          <Icon name={menuOpen ? "close" : "menu"} size={22} />
        </Button>
      </header>
      <aside
        onClick={closeOnLink}
        className={`${menuOpen ? "block" : "hidden"} border-b border-line bg-surface md:sticky md:top-0 md:block md:h-screen md:w-sidebar md:shrink-0 md:border-b-0 md:border-r`}
      >
        <Sidebar me={me.data} id="main-menu" />
      </aside>
      <main className="min-w-0 flex-1 px-4 pb-12 pt-6 md:px-[clamp(16px,3vw,40px)] md:pt-7">
        <div className="mx-auto max-w-[1360px]">
          <Outlet context={me.data} />
        </div>
      </main>
    </div>
  );
}
