// Activity rows for people: listening to a recording logs one entry per play, so a minute with a report reads as
// five identical rows. Back-to-back opens and plays of the same recording by the same person, each within
// GAP_MS of the next, show as one row with counts. Only the display is grouped; the audit log keeps every entry.

import type { AuditEntryItem } from "../../api/types";

const GAP_MS = 30 * 60_000;
const VIEWING = new Set(["recording.play", "analysis.view"]);

export interface ActivityRow {
  /** The newest entry in the group: its time, person and recording are the row's. */
  entry: AuditEntryItem;
  plays: number;
  views: number;
}

/** Groups entries listed newest first. */
export function groupViewing(entries: readonly AuditEntryItem[]): ActivityRow[] {
  const rows: ActivityRow[] = [];
  let oldestAt = 0; // time of the oldest entry in the last row
  for (const entry of entries) {
    const at = Date.parse(entry.at);
    const last = rows[rows.length - 1];
    const joins =
      last !== undefined &&
      VIEWING.has(entry.action) &&
      VIEWING.has(last.entry.action) &&
      entry.actor.id === last.entry.actor.id &&
      entry.target.type === last.entry.target.type &&
      entry.target.id === last.entry.target.id &&
      oldestAt - at <= GAP_MS;
    if (joins) {
      if (entry.action === "recording.play") last.plays += 1;
      else last.views += 1;
    } else {
      rows.push({
        entry,
        plays: entry.action === "recording.play" ? 1 : 0,
        views: entry.action === "analysis.view" ? 1 : 0,
      });
    }
    oldestAt = at;
  }
  return rows;
}

const times = (n: number) => (n === 1 ? "" : n === 2 ? " twice" : ` ${n} times`);

/** What a grouped row says, around the recording's name: "opened the report for" X " and played the audio 3 times". */
export function viewingWords(row: ActivityRow): { text: string; after: string } | null {
  if (row.plays + row.views <= 1) return null;
  if (row.views === 0) return { text: "played the audio of", after: times(row.plays) };
  if (row.plays === 0) return { text: "opened the report for", after: times(row.views) };
  const plays = row.plays === 1 ? "once" : row.plays === 2 ? "twice" : `${row.plays} times`;
  return { text: "opened the report for", after: ` and played the audio ${plays}` };
}
