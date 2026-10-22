// Small display helpers shared by the pages (P6.2).

import type { RecordingStatus } from "../design";
import type { ApiStatus, Role } from "../api/types";
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
