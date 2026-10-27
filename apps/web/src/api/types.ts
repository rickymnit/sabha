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
  /** Meetings: names people gave the anonymous voices ("S1" -> "Riya"). */
  voice_names: Record<string, string>;
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

/** GET /v1/recordings/{id}/speakers: who spoke how much, for a reviewer to say who is who (ADR 0007). */
export interface SpeakerSample {
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface ReviewSpeaker {
  /** As diarization named them: "S0", "S1". */
  label: string;
  /** Sabha's best guess at their role. */
  guess: string | null;
  talk_ms: number;
  /** Share of all speech, 0 to 1. */
  share: number;
  samples: SpeakerSample[];
}

export interface SpeakersResponse {
  recording_id: string;
  reason: string | null;
  /** The rubric's two roles, staff first ("teacher", "students"). */
  choices: string[];
  /** Most talk first. */
  speakers: ReviewSpeaker[];
}

export type ReviewDecision = { action: "confirm_roles"; staff_speaker: string } | { action: "close"; note: string };

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

/** One analysis of a recording (GET /v1/recordings/{id}/analyses), newest first. */
export interface AnalysisVersion {
  id: string;
  version: string;
  status: "COMPLETED" | "NEEDS_REVIEW";
  overall_score: number | null;
  rubric_id: string;
  rubric_version: string;
  /** A newer analysis of the recording exists. */
  superseded: boolean;
  /** ISO 8601 UTC. */
  created_at: string;
}

/** POST /v1/reanalysis. */
export interface BulkReanalysisRequest {
  type: string;
  reason: string;
  dry_run: boolean;
}

export interface BulkReanalysisResult {
  rubric_id: string;
  /** Finished recordings of the type scored with another rubric. */
  matching: number;
  started: number;
  remaining: number;
}

/** GET/PATCH /v1/settings (services/settings.py): owners and admins. */
export interface TenantSettings {
  name: string;
  profile: string;
  plan: string;
  labels: Labels & Record<string, string>;
  enabled_types: ConversationType[];
  /** Every type in the setup screen's order; `available` when the organisation has a rubric for it. */
  types: { type: ConversationType; enabled: boolean; available: boolean }[];
  /** How many types the plan allows on at once. */
  max_types: number;
}

/** PATCH /v1/settings: only what changes. */
export interface SettingsChange {
  name?: string;
  labels?: Partial<Labels>;
  enabled_types?: ConversationType[];
}

/** GET /v1/usage (services/usage.py): this month's audio hours (owners and admins). */
export interface UsageSummary {
  plan: string;
  used_hours: number;
  /** Set by Sabha for the tenant; null until agreed, and then there is no state or message either. */
  allowance_hours: number | null;
  state: "ok" | "warning" | "blocked" | "overage" | null;
  message: string | null;
  resets_at: string;
}

/** GET /v1/recordings/counts: the recordings of each type the signed-in person may see. */
export interface RecordingCounts {
  by_type: Partial<Record<ConversationType, number>>;
}

/** GET /v1/rubrics and /v1/rubrics/{id} (services/rubrics.py): read-only, for everyone signed in. */
export interface RubricVersion {
  id: string;
  version: string;
  in_use: boolean;
}

export interface RubricListItem {
  type: ConversationType;
  current_id: string;
  dimension_count: number;
  versions: RubricVersion[];
}

export interface RubricDetail {
  id: string;
  type: ConversationType;
  version: string;
  in_use: boolean;
  dimensions: {
    key: string;
    name: string;
    weight: number;
    definition: string;
    min_quotes: number;
    not_applicable_when: string | null;
    scale: { level: number; description: string; example: string | null }[];
  }[];
  versions: RubricVersion[];
  previous_id: string | null;
  /** From the version before: `item` is "weight", "definition", "anchors[2]", "examples[1]", "dimension added", ... */
  changes: { dimension: string | null; item: string; old: string | null; new: string | null }[];
}

/** GET /v1/audit (services/audit_log.py): who did what, newest first (owners and admins). */
export interface AuditEntryItem {
  id: string;
  at: string;
  action: string;
  /** `name` is null once the user no longer exists. */
  actor: { id: string; name: string | null; role: Role };
  /** `label`: a recording's title, a dispute's recording title or an invited person's name, where there is one. */
  target: { type: string; id: string; label: string | null };
  meta: Record<string, unknown>;
}

export interface AuditPage {
  items: AuditEntryItem[];
  next_cursor: string | null;
}
