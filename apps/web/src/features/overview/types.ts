// Overview numbers (P6.4b): the shape of GET /v1/overview?from&to. Every number comes with the count it is based
// on, so the page can hide a number whose underlying n is 0 instead of showing 0 or a placeholder.

import type { ConversationType } from "../../design";

export interface TypeMedian {
  type: ConversationType;
  /** Median verified overall score, 1 to 5. */
  median: number;
  /** Recordings with an overall score in the period. */
  n: number;
}

export interface CoachingItem {
  rubric_id: string;
  dimension_key: string;
  dimension_name: string;
  type: ConversationType;
  /** Median verified score for this dimension in the period. */
  median: number;
  /** Recordings with a verified score for this dimension. */
  n: number;
}

/** What is in the pipeline right now, by stage (GET /v1/overview `in_progress`; stages with none are left out). */
export interface StageCount {
  stage: "uploading" | "queued" | "preparing" | "finding_speakers" | "transcribing" | "analysing" | "needs_review";
  n: number;
}

export interface OverviewStats {
  /** Period as UTC instants, [from, to). */
  from: string;
  to: string;
  recordings_analysed: number;
  audio_hours: number;
  /** Not served yet (it is in each recording's segment map, not the database); the foot is left out without it. */
  silence_removed_hours?: number | null;
  median_overall_by_type: TypeMedian[];
  /** Not served until disputes are built; the tile is left out without it. */
  open_disputes?: number | null;
  /** Lowest median verified dimension scores in the period, lowest first. */
  coaching: CoachingItem[];
  in_progress?: StageCount[];
}
