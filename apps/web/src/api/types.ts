// Response shapes of the API, field for field (snake_case) with apps/api/sabha_api: routers/me.py,
// services/results.py and services/recordings.py. The report payload itself is features/report/types.ts.

import type { ConversationType } from "../design";
import type { Labels, TimeRange } from "../features/report/types";

export type Role = "owner" | "admin" | "manager" | "reviewer" | "staff";

export interface Me {
  /** `title` is the job title shown under the name ("Coordinator, Class 6"); display only. */
  user: { id: string; email: string; name: string; role: Role; title: string | null; unit_ids: string[] };
  tenant: {
    id: string;
    name: string;
    profile: string;
    /** The UI's nouns (CLAUDE.md: never hard-code "Teacher" or "Lesson"). */
    labels: Labels & Record<string, string>;
    enabled_types: ConversationType[];
    /** Every unit's name, so lists can say "Class 6" rather than an id. */
    units: { id: string; name: string }[];
  };
}

/** Recording statuses as the API stores them (sabha_core/state.py). */
export type ApiStatus =
  | "CREATED"
  | "UPLOADED"
  | "PREPROCESSING"
  | "DIARIZING"
  | "TRANSCRIBING"
  | "ANALYZING"
  | "COMPLETED"
  | "FAILED"
  | "NEEDS_REVIEW";

export interface RecordingItem {
  id: string;
  /** The file name without its extension. */
  title: string;
  type: ConversationType;
  status: ApiStatus;
  status_reason: string | null;
  /** Why it failed or needs review, in plain words; null otherwise. */
  status_note: string | null;
  person: { id: string; name: string } | null;
  unit_id: string | null;
  file_name: string | null;
  duration_ms: number | null;
  /** ISO 8601 UTC; shown in Asia/Kolkata. */
  created_at: string;
  status_changed_at: string | null;
  completed_at: string | null;
  /** The latest analysis's overall score, when there is one. */
  overall_score: number | null;
}

export interface RecordingPage {
  items: RecordingItem[];
  next_cursor: string | null;
}

export interface RecordingDetail extends RecordingItem {
  type_label: string;
  unit_name: string | null;
  recorded_at: string;
  speech_ms: number | null;
  languages: string[];
  removed_silence: TimeRange[];
}

export interface TranscriptResponse {
  recording_id: string;
  transcript: import("../features/transcript").Transcript;
  roles: Record<string, string>;
  roles_need_review: boolean;
  language_mix: Record<string, number>;
  playback_url: string;
  playback_expires_in_s: number;
}

export interface PersonItem {
  id: string;
  name: string;
  unit_id: string | null;
}

/** A row of the People page (GET /v1/people/summary): real counts and scores only. */
export interface PersonSummary extends PersonItem {
  /** Recordings with a completed analysis. */
  analysed: number;
  latest_score: number | null;
  /** Overall scores of the last 10 analysed recordings, oldest first. */
  recent_scores: number[];
  last_analysed_at: string | null;
}

export interface UploadPart {
  part_number: number;
  url: string;
}

export interface UploadStarted {
  recording_id: string;
  upload_id: string;
  part_size: number;
  parts: UploadPart[];
  expires_at: string;
}

/** A person on the local dev sign-in page (sabha_api.auth.dev_idp). */
export interface DevUser {
  subject: string;
  name: string;
  title: string | null;
  email: string;
  role: Role;
  tenant_id: string;
  tenant_name: string;
}

/** Recording states that are still moving through the pipeline (the list and page refresh while any are). */
export const IN_PROGRESS: ReadonlySet<ApiStatus> = new Set([
  "CREATED",
  "UPLOADED",
  "PREPROCESSING",
  "DIARIZING",
  "TRANSCRIBING",
  "ANALYZING",
]);
