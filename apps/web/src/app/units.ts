// The unit tree as the web app shows it (owner, 2026-10-28): top-level units ("Class 6") and the ones under them
// ("A"), named together as "Class 6 · A". The words for the two levels come from the tenant's labels.

import type { Me } from "../api/types";

export interface UnitNode {
  id: string;
  name: string;
  children: { id: string; name: string }[];
}

type Units = Me["tenant"]["units"];
type Labels = Me["tenant"]["labels"];

/** The two levels' words, with plain fallbacks for an older API answer. */
export function unitWords(labels: Labels) {
  return {
    group: labels.unit_group ?? "Group",
    groups: labels.unit_group_plural ?? "Groups",
    sub: labels.unit_sub ?? "Subgroup",
    subs: labels.unit_sub_plural ?? "Subgroups",
  };
}

/** Top-level units by name, each with the units under it by name. */
export function unitTree(units: Units): UnitNode[] {
  // Units without a number first ("LKG", "UKG"), then numbered ones by number ("Class 2" before "Class 10")
  const numbered = (name: string) => /\d/.test(name);
  const byName = (a: { name: string }, b: { name: string }) =>
    Number(numbered(a.name)) - Number(numbered(b.name)) || a.name.localeCompare(b.name, "en", { numeric: true });
  const tops = units.filter((u) => !u.parent_id || !units.some((p) => p.id === u.parent_id));
  return tops.sort(byName).map((top) => ({
    id: top.id,
    name: top.name,
    children: units.filter((u) => u.parent_id === top.id).sort(byName),
  }));
}

/** "Class 6 · A" for a unit under another, "Class 6" for a top-level one; "" when it is unknown. */
export function unitLabel(units: Units, id: string | null | undefined): string {
  const unit = id ? units.find((u) => u.id === id) : undefined;
  if (!unit) return "";
  const parent = unit.parent_id ? units.find((u) => u.id === unit.parent_id) : undefined;
  return parent ? `${parent.name} · ${unit.name}` : unit.name;
}
