// The Reviews queue (UI v2, docs/design/v2/05-reviews.png): open disputes (GET /v1/disputes) and recordings waiting
// for review (GET /v1/reviews) merged into one list, newest first, in three groups: disputes, "who is the speaker?"
// questions and everything else. Each item has a stable key used in the address (?item=d:<id> or /reviews/<id>).

import type { Me, RecordingItem } from "../../api/types";
import type { IconName } from "../../design";
import type { DisputePage } from "../disputes/types";

export type DisputeEntry = DisputePage["items"][number];
export type QueueGroup = "disputes" | "speakers" | "other";

export interface QueueItem {
  key: string;
  group: QueueGroup;
  icon: IconName;
  /** Tailwind classes for the icon tile. */
  tone: string;
  title: string;
  detail: string;
  /** ISO 8601 UTC: when it started waiting. */
  at: string;
  dispute?: DisputeEntry;
  recording?: RecordingItem;
}

const UNCLEAR_ROLES = "unclear_roles";

/** Short headings for the other reasons Sabha pauses on (sabha_core/reasons.py has the full sentences). */
const REVIEW_TITLES: Record<string, string> = {
  low_verification: "Scores could not be checked",
  unverified_dimensions: "Some scores could not be checked",
  uncertain_type: "What kind of conversation is this?",
  synthesis_failed: "Summary could not be written",
  ticket_failed: "Call ticket could not be written",
  no_speech: "No speech found",
  no_speakers: "Speakers could not be told apart",
  no_transcript: "No words recognised",
  too_short: "Very little speech",
};

export const disputeKey = (id: string) => `d:${id}`;
export const recordingKey = (id: string) => `r:${id}`;

export function buildQueue(
  disputes: readonly DisputeEntry[],
  recordings: readonly RecordingItem[],
  labels: Me["tenant"]["labels"],
): QueueItem[] {
  const fromDisputes = disputes
    .filter((d) => d.status === "open")
    .map<QueueItem>((d) => ({
      key: disputeKey(d.id),
      group: "disputes",
      icon: "message",
      tone: "bg-primary-tint text-primary",
      title: "Score dispute",
      detail: `${d.person_name ?? d.recording_title}: ${d.dimension_name.toLowerCase()}, ${d.current_score ?? d.ai_score} to ${d.proposed_score}`,
      at: d.created_at,
      dispute: d,
    }));
  const fromRecordings = recordings.map<QueueItem>((r) => {
    const roles = r.status_reason === UNCLEAR_ROLES;
    return {
      key: recordingKey(r.id),
      group: roles ? "speakers" : "other",
      icon: roles ? "people" : "alert",
      tone: roles ? "bg-warning-tint text-warning" : "bg-fill-2 text-ink-2",
      title: roles
        ? `Who is the ${labels.person.toLowerCase()}?`
        : (REVIEW_TITLES[r.status_reason ?? ""] ?? "Needs a person"),
      detail: roles ? `${r.title}: speaker roles unclear` : [r.title, r.status_note].filter(Boolean).join(": "),
      at: r.status_changed_at ?? r.created_at,
      recording: r,
    };
  });
  return [...fromDisputes, ...fromRecordings].sort((a, b) => b.at.localeCompare(a.at));
}

/** "Just now", "12 min", "2 h", "Yesterday", "3 days", then a date. */
export function waitingFor(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000));
  if (minutes < 2) return "Just now";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 14) return `${days} days`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
}

/** The first "mm:ss" or "h:mm:ss" time in a comment ("a thumbs-up check at 22:30"), in ms; null when none. */
export function timeInText(text: string): number | null {
  const match = /\b(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)\b/.exec(text);
  if (!match) return null;
  const [, h, m, s] = match;
  return ((Number(h ?? 0) * 60 + Number(m)) * 60 + Number(s)) * 1000;
}
