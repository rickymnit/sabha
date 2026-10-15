// The transcript@v1 shapes the web app reads. P3.7 writes them (transcript@v1.json) and serves them from
// GET /v1/recordings/{id}/transcript; the API client (P6.2 onwards) reuses these types. They mirror the contract
// in packages/asr/sabha_asr/schemas/transcript.v1.schema.json field for field (snake_case), so responses need no
// mapping. Change both together.

/**
 * A run of words in an utterance the speech recogniser was unsure of: a half-open [start, end) range of
 * `Utterance.text`, counted in Unicode code points (as Python indexes `str`), not UTF-16 code units.
 * `toUtf16Range` in `text.ts` converts it.
 */
export type LowConfidenceSpan = readonly [start: number, end: number];

/** One speaker turn. Times are milliseconds on the ORIGINAL recording timeline (silence already mapped back). */
export interface Utterance {
  /** A role from the rubric's `roles` list, for example "teacher" and "students", or "receptionist" and "caller". */
  role: string;
  /** The diarizer's anonymous label, for example "SPEAKER_00". Never a name. */
  speaker_label: string;
  start_ms: number;
  end_ms: number;
  text: string;
  /** Mean ASR word confidence for the utterance, 0 to 1. */
  avg_confidence: number;
  low_confidence_spans: LowConfidenceSpan[];
}

/** transcript@v1.json: utterances sorted by `start_ms`. */
export interface Transcript {
  version: "transcript@v1";
  /** Always the original recording, never the compact (silence-removed) audio. */
  timeline: "original";
  asr_model: string;
  word_count: number;
  utterances: Utterance[];
}

/** A presigned playback.opus URL and when it stops working. */
export interface PlaybackUrl {
  url: string;
  /** ISO 8601 UTC, for example "2026-10-15T09:30:00Z". */
  expires_at: string;
}

/**
 * How each role is shown: its label comes from the tenant's labels dictionary (for example labels.person for
 * "teacher"), never from a hard-coded word. `analysed` marks the staff member's role, drawn in the primary colour.
 */
export type RoleLabels = Readonly<Record<string, { label: string; analysed?: boolean }>>;
