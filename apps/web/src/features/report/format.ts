// Formatting for the report page. Times are stored in UTC and shown in Asia/Kolkata (CLAUDE.md API conventions).

import { formatClock } from "../transcript";
import type { Metric } from "./types";

const istDate = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
});
const istTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/** "13 Oct 2026, 10:05 am" in India Standard Time; "" for an unreadable date. */
export function formatIst(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return `${istDate.format(date)}, ${istTime.format(date).replace(/\s+/g, " ").toLowerCase()}`;
}

/** "38 min" (rounded to the nearest minute), "45 s" under a minute. */
export function formatMinutes(ms: number): string {
  if (ms < 60_000) return `${Math.round(Math.max(0, ms) / 1000)} s`;
  return `${Math.round(ms / 60_000)} min`;
}

/** "7 min 20 s", "45 s", "2 min". */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes === 0) return `${seconds} s`;
  return seconds === 0 ? `${minutes} min` : `${minutes} min ${seconds} s`;
}

/** "Hindi", "Hindi and English", "Hindi, Marathi and English". */
export function joinList(items: readonly string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** "25%" for a 0.25 rubric weight. */
export function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

/** A metric value in its unit; null for "not measured". */
export function formatMetricValue(metric: Pick<Metric, "value" | "unit">): string | null {
  const { value, unit } = metric;
  if (value === null || !Number.isFinite(value)) return null;
  switch (unit) {
    case "ratio":
      return formatPercent(value);
    case "count":
      return String(Math.round(value));
    case "wpm":
      return `${Math.round(value)} wpm`;
    case "ms":
      return formatDuration(value);
  }
}

/** "11:20 to 18:40". */
export function formatRange(range: { start_ms: number; end_ms: number }): string {
  return `${formatClock(range.start_ms)} to ${formatClock(range.end_ms)}`;
}

/** Score with one decimal, as the overall score is stored. */
export function formatScore(score: number): string {
  return score.toFixed(1);
}

/** "introduction" -> "Introduction"; labels the model writes in lower case. */
export function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Under the overall score: how many rubric scores are backed by quotes the grounding check found. */
export function checkedText(dimensions: readonly { verified: boolean }[]): string {
  const checked = dimensions.filter((d) => d.verified).length;
  if (dimensions.length === 0) return "";
  if (checked === dimensions.length) {
    return `All ${checked} scores are backed by quotes found in the transcript.`;
  }
  return `${checked} of ${dimensions.length} scores are backed by quotes found in the transcript.`;
}
