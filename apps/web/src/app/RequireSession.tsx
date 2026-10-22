import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useSession } from "../session/session";

/** Sends people who are not signed in to /login, remembering where they were going. */
export function RequireSession() {
  const session = useSession();
  const location = useLocation();
  if (!session.ready) return null;
  if (!session.token) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}
