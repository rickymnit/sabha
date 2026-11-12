// Plain helpers for the sales rep's workspace: the name a conversation goes by, a next action as an instruction,
// dates, a pending status. Built so a page reads at a glance (manager's feedback, 2026-11-12): a client's name or
// "Call on 5 Nov", never a file name.

import { formatWhen } from "../../app/format";

const DUE = new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/** "Thu, 12 Nov" for a due date (YYYY-MM-DD); "Overdue · Thu, 12 Nov"; or the words as said; or null. */
export function dueText(item: { due_date: string | null; due_said: string | null; overdue: boolean }): string | null {
  if (item.due_date) {
    const day = DUE.format(new Date(`${item.due_date}T00:00:00Z`));
    return item.overdue ? `Overdue · ${day}` : `Due ${day}`;
  }
  return item.due_said ? `When: “${item.due_said}”` : null;
}

/** The client: as typed at upload, else as said in the conversation. */
export function clientOf(row: { client_name?: string | null; client_said?: string | null }): string | null {
  return row.client_name || row.client_said || null;
}

export function kindWord(kind: "call" | "meeting" | null | undefined): "Call" | "Meeting" {
  return kind === "call" ? "Call" : "Meeting";
}

/** What a conversation is called: the client's name, else "Call on 5 Nov" / "Meeting today, 11:20". */
export function conversationName(
  client: string | null | undefined,
  kind: "call" | "meeting" | null | undefined,
  at: string,
  now: Date = new Date(),
): string {
  if (client) return client;
  const when = formatWhen(at, now);
  const relative = when.startsWith("Today") || when.startsWith("Yesterday");
  return `${kindWord(kind)} ${relative ? when.charAt(0).toLowerCase() + when.slice(1) : `on ${when}`}`;
}

const REP_WILL = /^(?:the\s+)?(?:sales\s+)?(?:rep|representative)\s+(?:will|should|is going to|has to|needs to)\s+/i;

/** A next action as an instruction to the rep: "The rep will send the brochure." becomes "Send the brochure."
 *  (older analyses; deal card prompt v4 writes instructions). The customer's part is left as written. */
export function plainAction(text: string): string {
  const rest = text.trim().replace(REP_WILL, "");
  return rest === text.trim() ? rest : rest.charAt(0).toUpperCase() + rest.slice(1);
}

/** What to say instead of a score while a call or meeting is not finished. */
export function pendingWords(status: string): string {
  if (status === "FAILED") return "Could not be analysed";
  if (status === "NEEDS_REVIEW") return "Waiting for a review";
  return "Being analysed…";
}
