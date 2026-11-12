import { describe, expect, it } from "vitest";

import type { Me } from "../api/types";
import { navItems } from "./nav";
import { isSalesRep } from "./workspace";
import { scoreWord } from "../design";
import { conversationName, plainAction } from "../features/workspace/words";

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
    expect(isSalesRep(me("staff", ["teaching", "sales"], null))).toBe(false); // a new teacher
    expect(isSalesRep(me("manager", ["sales"], ["sales"]))).toBe(false); // managers keep the Overview
  });

  it("has four simple pages and nothing else", () => {
    const labels = navItems(me("staff", ["sales"], ["sales"])).map((n) => n.label);
    expect(labels).toEqual(["Overview", "My interactions", "My next actions", "Private coaching"]);
  });
});

describe("reading the workspace at a glance", () => {
  const now = new Date("2026-11-12T10:00:00+05:30");

  it("names a conversation by its client, else by kind and day, never by file name", () => {
    expect(conversationName("Sunrise School", "call", "2026-11-05T06:00:00Z", now)).toBe("Sunrise School");
    expect(conversationName(null, "call", "2026-11-05T06:00:00Z", now)).toBe("Call on 5 Nov");
    expect(conversationName(null, "meeting", "2026-11-12T03:30:00Z", now)).toBe("Meeting today, 09:00");
  });

  it("turns older next actions into instructions, and leaves the client's part alone", () => {
    expect(plainAction("The rep will send the product brochure on WhatsApp.")).toBe(
      "Send the product brochure on WhatsApp.",
    );
    expect(plainAction("Sales rep should call back on Monday")).toBe("Call back on Monday");
    expect(plainAction("The customer will come back to the rep.")).toBe("The customer will come back to the rep.");
  });

  it("says what a score means in a word", () => {
    expect([2.2, 3.0, 3.75, 4.6].map(scoreWord)).toEqual(["Needs work", "Fair", "Strong", "Strong"]);
  });
});
