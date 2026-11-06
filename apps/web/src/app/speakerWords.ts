// The words around "who spoke when" strips in lists (UI v2, docs/design/v2/01-overview.png, 02-recordings.png): the
// caption under each row ("Teacher 62%", "Staff 45%") and the legend above the table ("Staff speaking", "Students
// or callers"). The staff word comes from the tenant's labels; a reception call's staff are front-desk staff, a
// support call's are agents and a sales call's are sales reps (a company's person word, "Team member", is general).

import type { Me, RecordingItem } from "../api/types";
import type { ConversationType } from "../design";
import { capitalise } from "./format";

type Labels = Me["tenant"]["labels"];

/** Who the blue side is in one recording. */
export function staffWord(type: RecordingItem["type"], labels: Labels): string {
  if (type === "reception") return "Staff";
  if (type === "sales") return "Sales rep";
  return type === "support" ? "Agent" : capitalise(labels.person);
}

const OTHERS: Partial<Record<ConversationType, string>> = {
  teaching: "students",
  reception: "callers",
  support: "customers",
};

/** The amber side across the types switched on: "Students or callers", or "Others". */
export function othersWord(enabled: readonly string[]): string {
  const words = [...new Set(enabled.map((t) => OTHERS[t as ConversationType] ?? "others"))];
  const last = words.pop() ?? "others";
  return capitalise(words.length ? `${words.join(", ")} or ${last}` : last);
}
