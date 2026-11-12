import { Navigate, useOutletContext } from "react-router-dom";

import type { Me } from "../api/types";
import { isSalesRep } from "./workspace";

/** Where "/" goes: the Overview for people who look after others, a sales rep's own workspace, or the progress
 * page for other staff. */
export function Home() {
  const me = useOutletContext<Me>();
  const to = isSalesRep(me) ? "/my" : me.user.role === "staff" ? "/progress" : "/overview";
  return <Navigate to={to} replace />;
}
