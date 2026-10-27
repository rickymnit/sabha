// Pages for some roles only (P6.8). The menu already hides them from everyone else; this also covers a typed or
// shared address, sending the person to their own start page. What anyone may read is still decided by the API.

import { Navigate, Outlet, useOutletContext } from "react-router-dom";

import type { Me, Role } from "../api/types";

export function RoleGate({ roles }: { roles: readonly Role[] }) {
  const me = useOutletContext<Me>();
  if (!roles.includes(me.user.role)) return <Navigate to="/" replace />;
  return <Outlet context={me} />;
}
