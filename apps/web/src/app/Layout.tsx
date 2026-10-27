// The app shell (UI v2 sidebar, docs/design/v2/*.png): logo, the school, navigation in the tenant's own
// words, the conversation types it has switched on, and the signed-in person. On phones the sidebar becomes a top bar
// with a menu button. Every noun comes from GET /v1/me labels (CLAUDE.md: never hard-code "Teacher" or "Lesson").
// Only finished pages are in the menu (app/nav.ts).

import { useState, type MouseEvent, type ReactNode } from "react";
import { Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useDisputes, useLiveEvents, useMe, useRecordingCounts, useReviews, useUsage } from "../api/hooks";
import type { Me } from "../api/types";
import { Avatar, Button, EmptyState, Icon, Logo, NavItem, initials } from "../design";
import { useSession } from "../session/session";
import { capitalise, roleTitle, unitNames } from "./format";
import { ADMINS, RESOLVERS, navItems } from "./nav";
import { AppLoading } from "./AppLoading";
import { HeaderSearch } from "./HeaderSearch";
import { PlanUsage } from "./PlanUsage";

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
  const units = unitNames(me, 1);
  const resolver = RESOLVERS.includes(me.user.role);
  const reviews = useReviews(resolver);
  const disputes = useDisputes(resolver);
  const counts = useRecordingCounts();
  const usage = useUsage(ADMINS.includes(me.user.role));
  // The menu's extras never break a page: an answer of an unexpected shape just leaves them out.
  const typeCounts = typeof counts.data?.by_type === "object" ? counts.data.by_type : undefined;
  const planUsage = typeof usage.data?.used_hours === "number" ? usage.data : undefined;
  const waiting = (reviews.data?.items.length ?? 0) + (disputes.data?.items.filter((d) => !d.raised_by_me).length ?? 0);
  return (
    <nav id={id} aria-label="Main" className="flex h-full flex-col gap-6 px-3.5 py-5">
      <div className="hidden px-2 md:block">
        <Logo />
      </div>
      <div className="flex items-center gap-2.5 rounded-card border border-line bg-surface px-2.5 py-2">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded bg-primary-tint text-caption font-bold text-primary"
        >
          {initials(me.tenant.name)}
        </span>
        <div className="min-w-0">
          <p className="m-0 truncate text-sm font-semibold text-ink">{me.tenant.name}</p>
          <p className="m-0 truncate text-caption text-muted">
            {[capitalise(me.tenant.profile), units].filter(Boolean).join(", ")}
          </p>
        </div>
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
            <Link
              key={t}
              to={`/recordings?type=${t}`}
              type={t}
              current={pathname === "/recordings" && type === t}
              {...(typeCounts ? { count: typeCounts[t] ?? 0 } : {})}
            >
              {capitalise(t)}
            </Link>
          ))}
        </div>
      )}
      <div className="mt-auto flex flex-col gap-3">
        {planUsage && <PlanUsage usage={planUsage} />}
        <div className="flex items-center gap-2.5 px-1">
          <Avatar name={me.user.name} tone="ink" />
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-semibold text-ink">{me.user.name}</span>
            <span className="text-caption leading-snug text-muted-2">{roleTitle(me.user, labels)}</span>
          </div>
          <Button variant="ghost" aria-label="Sign out" title="Sign out" onClick={signOut} className="text-muted-2">
            <Icon name="signOut" />
          </Button>
        </div>
      </div>
    </nav>
  );
}

/** The bar above every page (UI v2): search, and Upload for everyone (staff upload for themselves). */
function Header({ me }: { me: Me }) {
  const navigate = useNavigate();
  return (
    <div className="border-b border-line bg-surface px-4 py-2.5 md:sticky md:top-0 md:z-10 md:px-[clamp(16px,3vw,40px)]">
      <div className="mx-auto flex max-w-[1360px] items-center gap-2.5">
        <HeaderSearch me={me} />
        <div className="ml-auto flex items-center gap-2.5">
          <Button icon={<Icon name="upload" size={16} />} onClick={() => navigate("/upload")}>
            Upload
          </Button>
        </div>
      </div>
    </div>
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

  if (me.isPending) return <AppLoading label="Loading your workspace" />;
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
        aria-label="Menu"
        onClick={closeOnLink}
        className={`${menuOpen ? "block" : "hidden"} border-b border-line bg-surface md:sticky md:top-0 md:block md:h-screen md:w-sidebar md:shrink-0 md:border-b-0 md:border-r`}
      >
        <Sidebar me={me.data} id="main-menu" />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <Header me={me.data} />
        <main className="min-w-0 flex-1 px-4 pb-12 pt-6 md:px-[clamp(16px,3vw,40px)] md:pt-7">
          <div className="mx-auto max-w-[1360px]">
            <Outlet context={me.data} />
          </div>
        </main>
      </div>
    </div>
  );
}
