// The Overview's tiles and coaching rows (UI v2, docs/design/v2/01-overview.png), worked out from GET /v1/overview.
// A number whose underlying count is 0 is left out, never shown as 0 (golden rule 6). The "up / down" text compares
// with the period before (`series`); the bars are the eight periods, oldest first, the last one this period.

import type { ConversationType } from "../../design";
import type { Labels } from "../report/types";
import type { CoachingItem, OverviewStats, PeriodStats } from "./types";

export type TypeNames = Record<ConversationType, string>;

export const MAX_COACHING_ROWS = 6;
/** The unit switcher's "All". */
export const ALL_UNITS = "all";

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** "162", "41.5", "0.3": one decimal under 100 hours, whole hours above. */
export function formatHours(hours: number): string {
  return hours >= 100 ? String(Math.round(hours)) : String(Math.round(hours * 10) / 10);
}

export type Trend = "up" | "down" | "same";

export interface Tile {
  id: string;
  label: string;
  value: string;
  suffix?: string;
  foot?: string;
  /** Colour of the foot: good news green, bad news red, otherwise muted. */
  footTone: "good" | "bad" | "muted";
  /** One bar per period, oldest first, 0 to 1; null where that period has no data. */
  bars: (number | null)[];
  /** Screen-reader summary of the bars. */
  barsLabel: string;
}

/** The type most analysed this period: the one the median tile and the coaching table speak about. */
export function mainType(stats: OverviewStats): ConversationType | null {
  const best = [...stats.median_overall_by_type].filter((t) => t.n > 0).sort((a, b) => b.n - a.n)[0];
  return best?.type ?? stats.coaching[0]?.type ?? null;
}

const median = (p: PeriodStats, type: ConversationType) => p.median_overall_by_type.find((t) => t.type === type);
const resolvedShare = (p: PeriodStats) => (p.tickets ? (p.tickets_resolved ?? 0) / p.tickets : null);

function scaled(values: (number | null)[], max?: number): (number | null)[] {
  const top = max ?? Math.max(0, ...values.map((v) => v ?? 0));
  return values.map((v) => (v === null ? null : top > 0 ? v / top : 0));
}

function delta(now: number, before: number | null, unit: string, compare: string, places = 0): [string, Trend] {
  if (before === null) return ["", "same"];
  const diff = Number((now - before).toFixed(places));
  if (diff === 0) return [`Same as ${compare}`, "same"];
  const size = Math.abs(diff).toFixed(places);
  return [`${diff > 0 ? "Up" : "Down"} ${size}${unit} on ${compare}`, diff > 0 ? "up" : "down"];
}

const tone = (trend: Trend, upIsGood = true): Tile["footTone"] =>
  trend === "same" ? "muted" : (trend === "up") === upIsGood ? "good" : "bad";

/**
 * The four tiles: recordings analysed, audio processed, the main type's median score and, with reception switched
 * on and tickets this period, calls resolved. `compare` names the previous period ("last week").
 */
export function overviewTiles(
  stats: OverviewStats,
  typeNames: TypeNames,
  labels: Labels,
  compare: string,
  enabledTypes: readonly ConversationType[],
): Tile[] {
  const series = stats.series?.length ? stats.series : [stats];
  const before = series.length > 1 ? (series[series.length - 2] ?? null) : null;
  const tiles: Tile[] = [];
  const n = stats.recordings_analysed;
  if (n <= 0) return tiles;
  const things = labels.recording_plural.toLowerCase();

  const [analysedFoot, analysedTrend] = delta(n, before?.recordings_analysed ?? null, "", compare);
  tiles.push({
    id: "analysed",
    label: `${capitalise(labels.recording_plural)} analysed`,
    value: String(n),
    foot: analysedFoot,
    footTone: tone(analysedTrend),
    bars: scaled(series.map((p) => p.recordings_analysed)),
    barsLabel: `${things} analysed per period: ${series.map((p) => p.recordings_analysed).join(", ")}`,
  });

  tiles.push({
    id: "audio",
    label: "Audio processed",
    value: formatHours(stats.audio_hours),
    suffix: " h",
    ...(stats.silence_n && typeof stats.silence_hours === "number"
      ? { foot: `${formatHours(stats.silence_hours)} h of silence skipped` }
      : {}),
    footTone: "muted",
    bars: scaled(series.map((p) => p.audio_hours)),
    barsLabel: `Audio hours per period: ${series.map((p) => formatHours(p.audio_hours)).join(", ")}`,
  });

  const main = mainType(stats);
  const current = main ? median(stats, main) : undefined;
  if (main && current && current.n > 0) {
    const previous = before ? median(before, main) : undefined;
    const [foot, trend] = delta(current.median, previous?.n ? previous.median : null, "", compare, 1);
    const medians = series.map((p) => median(p, main)?.median ?? null);
    tiles.push({
      id: `median-${main}`,
      label: `Median ${typeNames[main].toLowerCase()} score`,
      value: current.median.toFixed(1),
      suffix: " / 5",
      foot: foot || `From ${current.n} ${(current.n === 1 ? labels.recording : labels.recording_plural).toLowerCase()}`,
      footTone: tone(trend),
      bars: scaled(medians, 5),
      barsLabel: `Median score per period: ${medians.map((m) => (m === null ? "none" : m.toFixed(1))).join(", ")}`,
    });
  }

  const share = resolvedShare(stats);
  if (enabledTypes.includes("reception") && share !== null) {
    const pct = Math.round(share * 100);
    const beforeShare = before ? resolvedShare(before) : null;
    const [foot, trend] = delta(pct, beforeShare === null ? null : Math.round(beforeShare * 100), " points", compare);
    const shares = series.map(resolvedShare);
    tiles.push({
      id: "resolved",
      label: `${typeNames.reception} calls resolved`,
      value: String(pct),
      suffix: "%",
      foot: foot || `Of ${stats.tickets} calls`,
      footTone: tone(trend),
      bars: scaled(shares, 1),
      barsLabel: `Calls resolved per period: ${shares.map((s) => (s === null ? "none" : `${Math.round(s * 100)}%`)).join(", ")}`,
    });
  }
  return tiles;
}

/** The coaching table's rows: the main type's dimensions with data, lowest median first. */
export function coachingRows(stats: OverviewStats): CoachingItem[] {
  const main = mainType(stats);
  return stats.coaching
    .filter((i) => i.n > 0 && (main === null || i.type === main))
    .sort((a, b) => a.median - b.median || b.n - a.n)
    .slice(0, MAX_COACHING_ROWS);
}
