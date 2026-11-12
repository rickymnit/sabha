// Plain helpers for the sales rep's workspace (dates, the client, a pending status).

const DUE = new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/** "Thu, 12 Nov" for a due date (YYYY-MM-DD); "Overdue · Thu, 12 Nov"; or the words as said; or null. */
export function dueText(item: { due_date: string | null; due_said: string | null; overdue: boolean }): string | null {
  if (item.due_date) {
    const day = DUE.format(new Date(`${item.due_date}T00:00:00Z`));
    return item.overdue ? `Overdue · ${day}` : day;
  }
  return item.due_said ? `“${item.due_said}”` : null;
}

/** The client: as typed at upload, else as said in the conversation. */
export function clientOf(row: { client_name?: string | null; client_said?: string | null }): string | null {
  return row.client_name || row.client_said || null;
}

/** What to say instead of a score while a call or meeting is not finished. */
export function pendingWords(status: string): string {
  if (status === "FAILED") return "Could not be analysed";
  if (status === "NEEDS_REVIEW") return "Waiting for a review";
  return "Being analysed…";
}
