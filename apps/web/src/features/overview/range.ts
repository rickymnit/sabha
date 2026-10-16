// Date ranges for the overview, in India Standard Time (CLAUDE.md: times are stored in UTC, shown in IST).
// A range is a pair of IST calendar days, both included; the API gets the UTC instants [start 00:00, end + 1 00:00).

export type RangePreset = "7d" | "30d" | "month" | "custom";

export interface DayRange {
  /** "YYYY-MM-DD", IST calendar days, both included. */
  start: string;
  end: string;
}

const IST_OFFSET_MS = 330 * 60_000;
const DAY_MS = 86_400_000;
const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
export const MAX_RANGE_DAYS = 366;

function dayToUtcMs(day: string): number {
  const match = DAY.exec(day);
  if (!match) throw new Error(`not a YYYY-MM-DD day: ${day}`);
  const [, y, m, d] = match;
  const ms = Date.UTC(Number(y), Number(m) - 1, Number(d));
  if (new Date(ms).toISOString().slice(0, 10) !== day) throw new Error(`not a calendar day: ${day}`);
  return ms;
}

const msToDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export function isDay(value: string): boolean {
  try {
    dayToUtcMs(value);
    return true;
  } catch {
    return false;
  }
}

/** Today's date in India. */
export function istToday(now: Date): string {
  return msToDay(now.getTime() + IST_OFFSET_MS);
}

export function addDays(day: string, days: number): string {
  return msToDay(dayToUtcMs(day) + days * DAY_MS);
}

export function presetRange(preset: Exclude<RangePreset, "custom">, now: Date): DayRange {
  const end = istToday(now);
  switch (preset) {
    case "7d":
      return { start: addDays(end, -6), end };
    case "30d":
      return { start: addDays(end, -29), end };
    case "month":
      return { start: `${end.slice(0, 8)}01`, end };
  }
}

/** Why a custom range cannot be used, or null if it can. */
export function rangeProblem(range: DayRange, now: Date): string | null {
  if (!isDay(range.start) || !isDay(range.end)) return "Choose both dates.";
  if (range.start > range.end) return "The start date must be on or before the end date.";
  if (range.end > istToday(now)) return "The end date cannot be in the future.";
  const days = (dayToUtcMs(range.end) - dayToUtcMs(range.start)) / DAY_MS + 1;
  if (days > MAX_RANGE_DAYS) return `Choose at most ${MAX_RANGE_DAYS} days.`;
  return null;
}

/** The UTC instants for GET /v1/overview?from&to: IST midnight at the start, IST midnight after the end. */
export function toQuery(range: DayRange): { from: string; to: string } {
  return {
    from: new Date(dayToUtcMs(range.start) - IST_OFFSET_MS).toISOString(),
    to: new Date(dayToUtcMs(range.end) + DAY_MS - IST_OFFSET_MS).toISOString(),
  };
}

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** "6 to 12 October 2026", "28 September to 4 October 2026", "12 October 2026" (Main.dc.html:89). */
export function describeRange({ start, end }: DayRange): string {
  const [sy, sm, sd] = start.split("-").map(Number) as [number, number, number];
  const [ey, em, ed] = end.split("-").map(Number) as [number, number, number];
  const endText = `${ed} ${MONTHS[em - 1]} ${ey}`;
  if (start === end) return endText;
  if (sy !== ey) return `${sd} ${MONTHS[sm - 1]} ${sy} to ${endText}`;
  if (sm !== em) return `${sd} ${MONTHS[sm - 1]} to ${endText}`;
  return `${sd} to ${endText}`;
}
