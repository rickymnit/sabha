import { describe, expect, it } from "vitest";

import { bestAndWorst, nextStep } from "./answer";
import type { AnalysisReport, VerifiedDimension } from "./types";

const dim = (key: string, score: number, override?: number) =>
  ({ key, name: key, score, verified: true, rationale: "", evidence: [], weight: 1,
     ...(override ? { override: { score: override } } : {}) }) as unknown as VerifiedDimension; // prettier-ignore

const ev = { utterance_id: "u1", start_ms: 5_000, quote: "q" };

describe("the report's answer first", () => {
  it("picks the best and the lowest verified points, a reviewer's score first", () => {
    expect(bestAndWorst([dim("a", 2), dim("b", 4), dim("c", 3, 1)])).toMatchObject({
      best: { key: "b" },
      worst: { key: "c" },
    });
    expect(bestAndWorst([dim("a", 4), dim("b", 5)])).toMatchObject({ best: { key: "b" }, worst: null }); // all Strong
    expect(bestAndWorst([dim("a", 2), dim("b", 2)]).best).toBeNull(); // nothing better than the lowest
  });

  it("finds the agreed next step whatever the kind of conversation", () => {
    const base = { deal_card: null, case_card: null, ticket: null, meeting_notes: null } as unknown as AnalysisReport;
    expect(nextStep(base)).toBeNull();
    const deal = {
      ...base,
      deal_card: { next_step: { action: "Send the quote", owner: "sales_rep", due: "kal", evidence: ev } },
    };
    expect(nextStep(deal as unknown as AnalysisReport)).toEqual({
      text: "Send the quote",
      who: "The rep",
      when: "kal",
      ms: 5_000,
    });
    const notes = {
      ...base,
      meeting_notes: { action_items: [{ action: "Book the hall", owner: "Meena", due: null, evidence: ev }] },
    };
    expect(nextStep(notes as unknown as AnalysisReport)?.who).toBe("Meena");
  });
});
