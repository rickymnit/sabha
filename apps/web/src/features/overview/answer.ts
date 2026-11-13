// The Overview's answer first (manager's feedback, 2026-11-13: "I have to concentrate too hard; make it so I get it
// at a glance"): one sentence on how the team is doing, what is going well, what needs work, and each person with
// one word and one reason. Every word here is worked out in code from verified scores (golden rule 5); nothing is
// written by the model.

import { scoreBand, scoreWord, type ScoreBand } from "../../design";
import type { Labels } from "../report/types";
import { mainType } from "./metrics";
import type { CoachingItem, OverviewStats } from "./types";

/** A person as GET /v1/people/summary gives them. */
export interface PersonRow {
  id: string;
  name: string;
  analysed: number;
  recent_scores: number[];
  weakest?: { name: string; median: number; n: number } | null;
  strongest?: { name: string; median: number; n: number } | null;
}

export const RECENT_COUNT = 5;

/** A person's level: the mean of their last RECENT_COUNT overall scores, one decimal; null with none. */
export function recentLevel(scores: readonly number[]): number | null {
  const last = scores.slice(-RECENT_COUNT);
  if (last.length === 0) return null;
  return Math.round((last.reduce((a, b) => a + b, 0) / last.length) * 10) / 10;
}

export interface Headline {
  title: string;
  detail: string | null;
  band: ScoreBand | null;
}

const TEAM_WORDS: Record<ScoreBand, string> = { good: "doing well", mid: "doing OK", low: "need help" };

/** "Your team members are doing OK." and why, from the period's median score and each person's recent level. */
export function overviewHeadline(stats: OverviewStats, people: readonly PersonRow[], labels: Labels): Headline {
  const who = `Your ${labels.person_plural.toLowerCase()}`;
  const type = mainType(stats);
  const median = stats.median_overall_by_type.find((t) => t.type === type && t.n > 0)?.median;
  if (median === undefined) {
    return {
      title: `No ${labels.recording_plural.toLowerCase()} scored in this period yet.`,
      detail: null,
      band: null,
    };
  }
  const band = scoreBand(median);
  const struggling = people.filter((p) => {
    const level = recentLevel(p.recent_scores);
    return level !== null && scoreBand(level) === "low";
  });
  const weakest = stats.coaching[0];
  const area = weakest ? `, mostly with ${weakest.dimension_name.toLowerCase()}` : "";
  const detail =
    struggling.length > 0
      ? `${struggling.length} ${struggling.length === 1 ? labels.person.toLowerCase() : labels.person_plural.toLowerCase()} ${struggling.length === 1 ? "needs" : "need"} help${area}.`
      : weakest && scoreBand(weakest.median) !== "good"
        ? `The weakest area is ${weakest.dimension_name.toLowerCase()}.`
        : null;
  return { title: `${who} ${band === "low" ? "need help" : `are ${TEAM_WORDS[band]}`}.`, detail, band };
}

export interface AreaCard {
  name: string;
  median: number;
  word: string;
  band: ScoreBand;
  n: number;
}

function card(item: CoachingItem | undefined): AreaCard | null {
  if (!item || item.n === 0) return null;
  return {
    name: item.dimension_name,
    median: item.median,
    word: scoreWord(item.median),
    band: scoreBand(item.median),
    n: item.n,
  };
}

/** The best and the worst rubric point of the period; "going well" only when it is at least Fair and not the same
 *  point as "needs work". */
export function areaCards(stats: OverviewStats): { good: AreaCard | null; work: AreaCard | null } {
  const items = stats.coaching.filter((c) => c.n > 0);
  const work = card(items[0]);
  const best = card(items.at(-1));
  const good = best && best.band !== "low" && items.length > 1 ? best : null;
  return { good, work: work && work.band !== "good" ? work : null };
}

export interface PersonLine {
  id: string;
  name: string;
  level: number;
  band: ScoreBand;
  word: string;
  reason: string;
}

/** Each person with recent scores: worst first, one word and one reason. */
export function personLines(people: readonly PersonRow[]): PersonLine[] {
  return people
    .flatMap((p) => {
      const level = recentLevel(p.recent_scores);
      if (level === null) return [];
      const band = scoreBand(level);
      const reason =
        band === "good" && p.strongest
          ? `Strong at ${p.strongest.name.toLowerCase()}`
          : p.weakest
            ? `Work on ${p.weakest.name.toLowerCase()}`
            : "Not enough scores to say why yet";
      return [{ id: p.id, name: p.name, level, band, word: scoreWord(level), reason }];
    })
    .sort((a, b) => a.level - b.level || a.name.localeCompare(b.name));
}
