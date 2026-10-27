// Small display helpers shared by the pages (P6.2).

import type { RecordingStatus } from "../design";
import type { ApiStatus, Me, Role } from "../api/types";
import type { ViewerRole } from "../features/report/types";

/** Times are stored in UTC and shown in Asia/Kolkata (CLAUDE.md API conventions). */
const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

const KOLKATA_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }); // YYYY-MM-DD
const KOLKATA_TIME = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
const KOLKATA_DATE = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" });
const KOLKATA_DATE_YEAR = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** Short and human, in Asia/Kolkata (Main.dc.html:186): "Today, 11:20", "Yesterday, 09:40", "10 Oct", "3 Mar 2025". */
export function formatWhen(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  const day = KOLKATA_DAY.format(when);
  const today = KOLKATA_DAY.format(now);
  const yesterday = KOLKATA_DAY.format(new Date(now.getTime() - 86_400_000));
  if (day === today) return `Today, ${KOLKATA_TIME.format(when)}`;
  if (day === yesterday) return `Yesterday, ${KOLKATA_TIME.format(when)}`;
  return day.slice(0, 4) === today.slice(0, 4) ? KOLKATA_DATE.format(when) : KOLKATA_DATE_YEAR.format(when);
}

/** "45 min", "1 h 05 min", or "" when unknown. */
export function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

/** The status chip and its words for each pipeline status (the text, not the colour, carries the meaning). */
export function statusChip(status: ApiStatus): { chip: RecordingStatus; text: string } {
  switch (status) {
    case "COMPLETED":
      return { chip: "analysed", text: "Analysed" };
    case "NEEDS_REVIEW":
      return { chip: "needs-review", text: "Needs review" };
    case "FAILED":
      return { chip: "failed", text: "Failed" };
    case "ANALYZING":
      return { chip: "analysing", text: "Analysing" };
    case "TRANSCRIBING":
      return { chip: "transcribing", text: "Transcribing" };
    case "DIARIZING":
      return { chip: "transcribing", text: "Finding speakers" };
    case "PREPROCESSING":
      return { chip: "transcribing", text: "Preparing audio" };
    case "UPLOADED":
      return { chip: "transcribing", text: "Queued" };
    case "CREATED":
      return { chip: "uploading", text: "Uploading" };
  }
}

/** The report's viewer roles: admins see notes about hidden output; managers and reviewers read as managers. */
export function viewerRole(role: Role): ViewerRole {
  if (role === "owner" || role === "admin") return "admin";
  if (role === "manager" || role === "reviewer") return "manager";
  return "staff";
}

export function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** What to call someone under their name: their job title, else their role in the tenant's own words. */
export function roleTitle(user: Me["user"], labels: Me["tenant"]["labels"]): string {
  if (user.title) return user.title;
  switch (user.role) {
    case "owner":
      return "Owner";
    case "admin":
      return "Administrator";
    case "manager":
      return capitalise(labels.manager);
    case "reviewer":
      return "Reviewer";
    case "staff":
      return capitalise(labels.person);
  }
}

/** The units someone belongs to, by name ("Class 6"); everyone's when they have none (owners and admins). */
export function unitNames(me: Me, max = 2): string {
  const byId = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  const names = (
    me.user.unit_ids.length ? me.user.unit_ids.map((id) => byId.get(id) ?? "") : [...byId.values()]
  ).filter(Boolean);
  if (names.length <= max) return names.join(", ");
  return `${names.slice(0, max).join(", ")} and ${names.length - max} more`;
}

/** Audio hours: "38.4", "2", "0.3"; one decimal, none when whole. */
export function formatHours(hours: number): string {
  return hours.toFixed(1).replace(/\.0$/, "");
}
