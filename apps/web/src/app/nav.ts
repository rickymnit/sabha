// The main menu. Only pages that are finished go in here: a menu item that opens a placeholder makes the whole
// product look unfinished. Add a page here in the same change that builds it.

import type { Me, Role } from "../api/types";
import type { IconName } from "../design";
import { capitalise } from "./format";
import { isSalesRep } from "./workspace";

export interface NavEntry {
  to: string;
  label: string;
  icon: IconName;
  /** Whether this entry is the current page. */
  match: (pathname: string) => boolean;
}

const EVERYONE: Role[] = ["owner", "admin", "manager", "reviewer", "staff"];
/** Who manages the organisation: settings and the plan's usage. */
export const ADMINS: Role[] = ["owner", "admin"];
/** Who resolves reviews (ADR 0007): never staff, not even for their own recordings. */
export const RESOLVERS: Role[] = ["owner", "admin", "manager", "reviewer"];

/** A sales rep's own workspace (founder's Sales Executive dashboard doc, 2026-11-12): four simple pages, nothing
 * else (manager's feedback, 2026-11-12). Adding a recording is the button in the top bar; how scoring works is linked
 * from Private coaching. */
function salesRepItems(): NavEntry[] {
  const exact = (to: string) => (path: string) => path === to;
  return [
    { to: "/my", label: "Overview", icon: "overview", match: exact("/my") },
    {
      to: "/my/interactions",
      label: "My interactions",
      icon: "recordings",
      match: (path) => path.startsWith("/my/interactions") || path.startsWith("/recordings/"),
    },
    { to: "/my/actions", label: "My next actions", icon: "checkList", match: exact("/my/actions") },
    { to: "/my/coaching", label: "Private coaching", icon: "spark", match: exact("/my/coaching") },
  ];
}

export function navItems(me: Me): NavEntry[] {
  if (isSalesRep(me)) return salesRepItems();
  const labels = me.tenant.labels;
  const entries: (NavEntry & { roles: Role[] })[] = [
    {
      to: "/overview",
      label: "Overview",
      icon: "overview",
      roles: ["owner", "admin", "manager", "reviewer"],
      match: (path) => path === "/overview",
    },
    {
      to: "/progress",
      label: "My progress",
      icon: "overview",
      roles: ["staff"], // the Overview's counterpart for the person analysed
      match: (path) => path === "/progress",
    },
    {
      to: "/recordings",
      label: capitalise(labels.recording_plural),
      icon: "recordings",
      roles: EVERYONE,
      match: (path) => path === "/recordings" || path.startsWith("/recordings/"),
    },
    {
      to: "/reviews",
      label: "Reviews",
      icon: "reviews",
      roles: RESOLVERS,
      match: (path) => path === "/reviews" || path.startsWith("/reviews/"),
    },
    {
      to: "/people",
      label: capitalise(labels.person_plural),
      icon: "people",
      roles: ["owner", "admin", "manager", "reviewer"], // staff see only themselves: no list to show
      match: (path) => path === "/people",
    },
    {
      to: "/rubrics",
      label: "Rubrics",
      icon: "rubrics",
      roles: EVERYONE, // staff read how they are scored (owner's decision, 2026-10-27)
      match: (path) => path === "/rubrics" || path.startsWith("/rubrics/"),
    },
    {
      to: "/upload",
      label: "Upload",
      icon: "upload",
      roles: EVERYONE,
      match: (path) => path === "/upload",
    },
    {
      to: "/activity",
      label: "Activity",
      icon: "clock",
      roles: ADMINS,
      match: (path) => path === "/activity",
    },
    {
      to: "/settings",
      label: "Settings",
      icon: "settings",
      roles: ADMINS,
      match: (path) => path === "/settings",
    },
  ];
  return entries.filter((entry) => entry.roles.includes(me.user.role));
}
