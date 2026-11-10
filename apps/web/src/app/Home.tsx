import { Navigate, useOutletContext } from "react-router-dom";

import type { Me } from "../api/types";

/** Where "/" goes: the Overview for people who look after others, their own progress page for staff. */
export function Home() {
  const me = useOutletContext<Me>();
  return <Navigate to={me.user.role === "staff" ? "/progress" : "/overview"} replace />;
}
