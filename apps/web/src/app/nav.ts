// The main menu. Only pages that are finished go in here: a menu item that opens a placeholder makes the whole
// product look unfinished. Add a page here in the same change that builds it.

import type { Me, Role } from "../api/types";
import type { IconName } from "../design";
import { capitalise } from "./format";

export interface NavEntry {
  to: string;
  label: string;
  icon: IconName;
  /** Whether this entry is the current page. */
  match: (pathname: string) => boolean;
}

const EVERYONE: Role[] = ["owner", "admin", "manager", "reviewer", "staff"];
/** Who resolves reviews (ADR 0007): never staff, not even for their own recordings. */
export const RESOLVERS: Role[] = ["owner", "admin", "manager", "reviewer"];

export function navItems(me: Me): NavEntry[] {
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
      to: "/upload",
      label: "Upload",
      icon: "upload",
      roles: EVERYONE,
      match: (path) => path === "/upload",
    },
    {
      to: "/settings",
      label: "Settings",
      icon: "settings",
      roles: ["owner", "admin"],
      match: (path) => path === "/settings",
    },
  ];
  return entries.filter((entry) => entry.roles.includes(me.user.role));
}
