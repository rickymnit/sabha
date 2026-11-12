// Who gets the sales rep's own workspace (founder's Sales Executive dashboard doc, 2026-11-12): staff whose linked
// person has sales recordings, or who have none yet in an organisation where sales is the only kind of conversation
// analysed for staff (team meetings aside): a new teacher in a school that also analyses sales is not a sales rep.
// Everyone else keeps their usual home (a teacher's My progress, the Overview for managers).

import type { Me } from "../api/types";

export function isSalesRep(me: Me): boolean {
  if (me.user.role !== "staff" || !me.tenant.enabled_types.includes("sales")) return false;
  const types = me.person?.types ?? [];
  if (types.includes("sales")) return true;
  return types.length === 0 && me.tenant.enabled_types.every((t) => t === "sales" || t === "meeting");
}
