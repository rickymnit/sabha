import { describe, expect, it } from "vitest";

import type { Me } from "../api/types";
import { navItems } from "./nav";
import { isSalesRep } from "./workspace";

function me(role: Me["user"]["role"], types: Me["tenant"]["enabled_types"], personTypes: string[] | null): Me {
  return {
    user: { id: "u", email: "u@example.com", name: "Rohit Rao", role, title: null, unit_ids: [] },
    tenant: {
      id: "t",
      name: "Acme",
      profile: "company",
      labels: { person: "Team member" } as Me["tenant"]["labels"],
      enabled_types: types,
      units: [],
    },
    person:
      personTypes === null ? null : { id: "p", name: "Rohit Rao", types: personTypes as Me["tenant"]["enabled_types"] },
  };
}

describe("the sales rep's workspace", () => {
  it("is for staff who make sales calls, or are new where only sales is analysed", () => {
    expect(isSalesRep(me("staff", ["sales", "support"], ["sales"]))).toBe(true);
    expect(isSalesRep(me("staff", ["sales", "meeting"], []))).toBe(true); // new, nothing recorded yet
    expect(isSalesRep(me("staff", ["sales", "support"], ["support"]))).toBe(false); // a support agent
    expect(isSalesRep(me("staff", ["sales", "support"], []))).toBe(false); // new, could be either
    expect(isSalesRep(me("manager", ["sales"], ["sales"]))).toBe(false); // managers keep the Overview
  });

  it("has four simple pages plus adding a recording", () => {
    const labels = navItems(me("staff", ["sales"], ["sales"])).map((n) => n.label);
    expect(labels).toEqual([
      "Overview",
      "My interactions",
      "My next actions",
      "Private coaching",
      "Add a recording",
      "Rubrics",
    ]);
  });
});
