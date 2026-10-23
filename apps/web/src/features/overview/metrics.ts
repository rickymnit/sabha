// The overview's headline numbers (P6.4b). A number whose underlying count is 0 is left out, not shown as 0.

import type { ConversationType, Metric } from "../../design";
import type { Labels } from "../report/types";
import type { CoachingItem, OverviewStats } from "./types";

export type TypeNames = Record<ConversationType, string>;

export const MAX_COACHING_ITEMS = 4;

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** "162", "41.5", "0.3": one decimal under 100 hours, whole hours above. */
export function formatHours(hours: number): string {
  return hours >= 100 ? String(Math.round(hours)) : String(Math.round(hours * 10) / 10);
}

export interface MetricSpec extends Omit<Metric, "foot"> {
  /** Foot text, or a link when `footHref` is set. */
  footText?: string;
  footHref?: string;
}

export function overviewMetrics(stats: OverviewStats, typeNames: TypeNames, labels: Labels): MetricSpec[] {
  const n = stats.recordings_analysed;
  if (n <= 0) return [];
  const metrics: MetricSpec[] = [
    { id: "analysed", label: `${capitalise(labels.recording_plural)} analysed`, value: String(n) },
    {
      id: "audio",
      label: "Audio processed",
      value: formatHours(stats.audio_hours),
      suffix: " h",
      ...(typeof stats.silence_removed_hours === "number"
        ? { footText: `${formatHours(stats.silence_removed_hours)} h of silence removed` }
        : {}),
    },
  ];
  for (const t of stats.median_overall_by_type) {
    if (t.n <= 0) continue;
    metrics.push({
      id: `median-${t.type}`,
      label: `Median ${typeNames[t.type].toLowerCase()} score`,
      value: t.median.toFixed(1),
      suffix: " / 5",
      footText: `From ${t.n} ${(t.n === 1 ? labels.recording : labels.recording_plural).toLowerCase()}`,
    });
  }
  if (typeof stats.open_disputes === "number") {
    metrics.push({
      id: "disputes",
      label: "Open disputes",
      value: String(stats.open_disputes),
      footText: "Review disputes",
      footHref: "/reviews",
    });
  }
  return metrics;
}

/** Items with data, lowest median first, at most MAX_COACHING_ITEMS. */
export function coachingItems(items: readonly CoachingItem[]): CoachingItem[] {
  return items
    .filter((i) => i.n > 0)
    .sort((a, b) => a.median - b.median || b.n - a.n)
    .slice(0, MAX_COACHING_ITEMS);
}
