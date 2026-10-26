// The analysis payload the recording report (P6.6) reads. The analysis API (P5.7b, GET /v1/recordings/{id}/analysis)
// is built to match these shapes field for field (snake_case), so responses need no mapping; the API client
// (P6.2 onwards) reuses this file. Every time is milliseconds on the ORIGINAL recording timeline.
//
// What the UI assumes (CLAUDE.md golden rule 5): numbers in `metrics` are computed in code, never by the LLM;
// a dimension is shown only when `verified` is true, and the UI checks that itself rather than trusting the API
// to have left unverified dimensions out.

/** One time range on the original recording timeline, half-open [start_ms, end_ms). */
export interface TimeRange {
  start_ms: number;
  end_ms: number;
}

/**
 * A transcript utterance id. Today the analysis stage uses index-based ids such as "u0042"; the format is being
 * settled with the transcript schema, so the UI treats it as opaque and finds lines by time instead.
 */
export type UtteranceId = string;

/** A quote the grounding verifier (P5.6) found in the transcript, with the matched utterance's corrected times. */
export interface EvidenceQuote extends TimeRange {
  quote: string;
  utterance_id: UtteranceId;
}

interface DimensionBase {
  /** Rubric dimension key, for example "checks_for_understanding". */
  key: string;
  /** Display name from the rubric, for example "Checks for understanding". */
  name: string;
  /** Rubric weight, 0 to 1 (0.2 is shown as "Weight 20%"). */
  weight: number;
}

/** A dimension whose every quote passed the grounding verifier. The only kind the report shows. */
export interface VerifiedDimension extends DimensionBase {
  verified: true;
  /** Whole number from 1 to 5. */
  score: number;
  /** The judge's reasoning, at most 60 words. */
  rationale: string;
  /** At least the rubric's min_quotes quotes, in time order. */
  evidence: EvidenceQuote[];
  /** "Try next time" text for this dimension. */
  suggestion?: string;
  /** A reviewer's score after an accepted dispute (P6.7). The AI score above stays as history. */
  override?: HumanOverride;
  /** A dispute about this score is waiting for a reviewer. */
  dispute_open?: boolean;
}

/** A person's score that replaces the AI score in the display; the AI score is kept and shown as history. */
export interface HumanOverride {
  /** Whole number from 1 to 5. */
  score: number;
  /** Role of the reviewer (never a name in the report payload). */
  reviewer_role: string;
  note: string;
  /** ISO 8601 UTC. */
  resolved_at: string;
}

/** The score to show: the reviewer's when there is one, otherwise the AI's. */
export function displayedScore(d: VerifiedDimension): number {
  return d.override?.score ?? d.score;
}

/**
 * A dimension that failed verification twice (P5.6). It is excluded from the overall score and never shown:
 * the API should send only key, name and weight, but the UI ignores any score, rationale or quotes it carries.
 */
export interface UnverifiedDimension extends DimensionBase {
  verified: false;
}

/**
 * A dimension the rubric allows to be "not applicable" (rubric `not_applicable_when`, for example escalation on a
 * call with nothing to escalate), verified as such: no score, left out of the overall score, with the reason and
 * the quotes that show it. Shown as a note, never as a score.
 */
export interface NotApplicableDimension extends DimensionBase {
  verified: true;
  not_applicable: true;
  score: null;
  rationale: string;
  evidence: EvidenceQuote[];
}

export type Dimension = VerifiedDimension | UnverifiedDimension | NotApplicableDimension;

/** How a metric value is formatted: ratio 0.16 → "16%", ms 440000 → "7 min 20 s". */
export type MetricUnit = "ratio" | "count" | "wpm" | "ms";

/** A number computed in code from the transcript (P5.5), never judged by the LLM. */
export interface Metric {
  /** Metric key, for example "teacher_talk_share". */
  key: string;
  /** Display name, already in the tenant's words (for example "Questions asked by teacher"). */
  name: string;
  /** null when it could not be measured (for example no speech from that role). */
  value: number | null;
  unit: MetricUnit;
  /** One-sentence definition shown in the tooltip. */
  definition: string;
  /** A computed breakdown shown under the value, for example "2 open, 9 recall". */
  detail?: string;
  /** Where the measured stretch is, for metrics such as the longest uninterrupted talk. */
  range?: TimeRange;
  /** A comparison computed from real data; omitted (never invented) when there is none. */
  median?: { scope: string; value: number } | null;
}

/** One of the three suggestions for the next session; each points at a moment in the recording. */
export interface Suggestion {
  text: string;
  utterance_id: UtteranceId;
  start_ms: number;
}

/** A part of the session, for example "Introduction". Optional: P5.7 does not produce phases yet. */
export interface Phase extends TimeRange {
  name: string;
}

export interface RubricRef {
  /** Rubric id, for example "teaching.school.v0.1". */
  id: string;
  /** For example "0.1". */
  version: string;
  /** Display name, for example "Teaching". */
  name: string;
}

export interface ModelInfo {
  /** The scoring model(s), for example ["model-2026-09"]. */
  ids: string[];
  /** Hash of the prompt files used, stored with the result (P5.6). */
  prompt_hash?: string;
}

/** Why the analysis is in its state, for example {code: "low_verification", message: "..."}. */
export interface StatusReason {
  code: string;
  /** Plain-language explanation for the person reading the report. */
  message: string;
}

/** Pipeline stages a processing recording can be in (sabha_core/state.py). */
export type PipelineStage = "uploaded" | "preprocessing" | "diarizing" | "transcribing" | "analyzing";

/** The report's content, present when the status is completed or partial. */
/** A deal card quote: the transcript's own words, with that line's times (verified like rubric evidence). */
export interface CardEvidence {
  quote: string;
  utterance_id: string;
  start_ms: number;
  end_ms: number;
}

/** Sales meetings: what the customer needs, their objections, interest and the agreed next step (verified only). */
export interface DealCard {
  /** What the customer uses today, what they pay, competitors they mention. */
  current_setup: { fact: string; evidence: CardEvidence }[];
  customer_needs: { need: string; evidence: CardEvidence }[];
  objections: { objection: string; response: string; settled: "yes" | "no" | "unclear"; evidence: CardEvidence }[];
  interest_level: { value: string; evidence: CardEvidence | null } | null;
  next_step: {
    action: string;
    owner: "sales_rep" | "customer" | "both";
    due: string | null;
    evidence: CardEvidence;
  } | null;
  /** Items left out because their quote was not found in the transcript. */
  left_out: number;
}

/** Reception calls and walk-in visits: category, outcome and follow-up, on two verified quotes. */
export interface Ticket {
  /** One of the rubric's categories, for example "appointment_or_meeting". */
  category: string;
  /** One of the rubric's statuses: "resolved", "follow_up_needed" or "escalated". */
  status: string;
  follow_up: { text: string; owner_role: string } | null;
  /** At most 60 words. */
  summary: string;
  /** Where the caller or visitor says what they need, and where the conversation reaches its outcome. */
  evidence: { need: CardEvidence; outcome: CardEvidence };
}

/** Meetings: decisions, action items and open questions, each on a verified quote. */
export interface MeetingNotes {
  decisions: { decision: string; evidence: CardEvidence }[];
  action_items: {
    action: string;
    /** As named in the meeting; null when nobody was named. */
    owner: string | null;
    /** The anonymous voice that took the work, when clear ("S2"); shown by the name people gave it. */
    owner_voice: string | null;
    due: string | null;
    evidence: CardEvidence;
  }[];
  open_questions: { question: string; evidence: CardEvidence }[];
  left_out: number;
}

export interface AnalysisReport {
  status: "completed" | "partial";
  /** Empty when completed; for partial, why some dimensions are missing. */
  reasons: StatusReason[];
  analysis_id: string;
  recording_id: string;
  /** ISO 8601 UTC. */
  created_at: string;
  rubric: RubricRef;
  model: ModelInfo;
  /** Weighted mean of verified dimensions, one decimal; null when under 60% of the weight is verified. */
  overall: number | null;
  /** The tenant- or unit-level median of overall scores, when there is real data for it. */
  comparison?: { scope: string; median: number } | null;
  /** The same person's recent range, when there is real data for it. */
  person_history?: { count: number; min: number; max: number } | null;
  dimensions: Dimension[];
  metrics: Metric[];
  /** At most 80 words. */
  summary: string;
  strengths: string[];
  gaps: string[];
  /** Exactly three. */
  suggestions: Suggestion[];
  phases?: Phase[] | null;
  /** Whether this viewer may dispute the scores (the person analysed, their managers, owners and admins). */
  can_dispute?: boolean;
  /** Reception only. */
  ticket?: Ticket | null;
  /** Sales meetings only. */
  deal_card?: DealCard | null;
  /** Meetings only. */
  meeting_notes?: MeetingNotes | null;
}

export interface AnalysisProcessing {
  status: "processing";
  reasons: StatusReason[];
  recording_id: string;
  stage: PipelineStage;
  /** Progress through the current stage, 0 to 1, when the stage reports it. */
  progress?: number | null;
  /** ISO 8601 UTC of the last update. */
  updated_at: string;
}

export interface AnalysisFailed {
  status: "failed";
  /** At least one. */
  reasons: StatusReason[];
  recording_id: string;
  /** Reference to quote when contacting support, for example the request or stage-run id. */
  reference?: string;
}

export interface AnalysisNeedsReview {
  status: "needs_review";
  /** At least one, for example low_verification. */
  reasons: StatusReason[];
  recording_id: string;
}

export type AnalysisPayload = AnalysisReport | AnalysisProcessing | AnalysisFailed | AnalysisNeedsReview;
export type AnalysisStatus = AnalysisPayload["status"];

/** Header details from the recording itself (GET /v1/recordings/{id}), not from the analysis. */
export interface ReportRecording {
  id: string;
  title: string;
  /** Conversation type's display name, for example "Teaching". */
  type_label: string;
  person: { id: string; name: string; unit: string };
  /** ISO 8601 UTC; shown in Asia/Kolkata. */
  recorded_at: string;
  duration_ms: number;
  /** Speech after silence removal; null until preprocessing has run. */
  speech_ms: number | null;
  /** Language names, for example ["Hindi", "English"]. */
  languages: string[];
  /** Silence the VAD removed (golden rule 4), on the original timeline; drawn grey on the timeline. */
  removed_silence: TimeRange[];
}

/** The tenant's words for its own nouns (sabha_core/profiles.py Labels). Never hard-code "Teacher" or "Lesson". */
export interface Labels {
  person: string;
  person_plural: string;
  recording: string;
  recording_plural: string;
  unit: string;
  manager: string;
}

/** Who is looking at the report; admins see notes about hidden, unverified output. */
export type ViewerRole = "admin" | "manager" | "staff";
