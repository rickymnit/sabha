import { describe, expect, it } from "vitest";

import type { Labels } from "../report/types";
import { areaCards, overviewHeadline, personLines, recentLevel } from "./answer";
import type { CoachingItem, OverviewStats } from "./types";

const LABELS = { person: "Team member", person_plural: "Team members", recording: "Conversation",
                 recording_plural: "Conversations", unit: "Team", manager: "Manager" } as Labels; // prettier-ignore

const item = (name: string, median: number, n = 4) =>
  ({ rubric_id: "r", dimension_key: name, dimension_name: name, type: "sales", median, n }) as CoachingItem;

function stats(median: number | null, coaching: CoachingItem[]): OverviewStats {
  return {
    from: "", to: "", recordings_analysed: 5, audio_hours: 1, coaching,
    median_overall_by_type: median === null ? [] : [{ type: "sales", median, n: 5 }],
  } as OverviewStats; // prettier-ignore
}

const person = (id: string, scores: number[], weakest?: string, strongest?: string) => ({
  id, name: id, analysed: scores.length, recent_scores: scores,
  weakest: weakest ? { name: weakest, median: 2, n: 3 } : null,
  strongest: strongest ? { name: strongest, median: 4, n: 3 } : null,
}); // prettier-ignore

describe("the Overview's answer first", () => {
  it("says in one sentence how the team is doing and who needs help with what", () => {
    const team = [person("Rohit", [2, 2.4]), person("Neha", [3.2, 3.4]), person("Pooja", [2.1])];
    expect(overviewHeadline(stats(2.9, [item("Opening the call", 1.5)]), team, LABELS)).toEqual({
      title: "Your team members need help.",
      detail: "2 team members need help, mostly with opening the call.",
      band: "low",
    });
    expect(overviewHeadline(stats(3.4, [item("Closing", 3.1)]), [person("Neha", [3.4])], LABELS).title).toBe(
      "Your team members are doing OK.",
    );
    expect(overviewHeadline(stats(null, []), [], LABELS).title).toBe("No conversations scored in this period yet.");
  });

  it("calls a point 'going well' only when it is at least Fair and not the one that needs work", () => {
    expect(areaCards(stats(3, [item("Opening", 1.5), item("Demo", 4.2)]))).toMatchObject({
      work: { name: "Opening", word: "Needs work" },
      good: { name: "Demo", word: "Strong" },
    });
    expect(areaCards(stats(2, [item("Opening", 1.5), item("Demo", 2.5)])).good).toBeNull();
    expect(areaCards(stats(4, [item("Demo", 4.2)]))).toEqual({ good: null, work: null });
  });

  it("lists people lowest first, each with one word and one reason", () => {
    const lines = personLines([
      person("Pooja", [4, 4.2, 4.4], "Pricing", "Demos"),
      person("Rohit", [5, 1, 2, 2, 2, 2], "Opening"), // only the last five count
      person("New", []),
    ]);
    expect(lines.map((l) => [l.name, l.word, l.reason])).toEqual([
      ["Rohit", "Needs work", "Work on opening"],
      ["Pooja", "Strong", "Strong at demos"],
    ]);
    expect(recentLevel([5, 1, 2, 2, 2, 2])).toBe(1.8);
  });
});
