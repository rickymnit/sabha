// Overview numbers (UI v2): the shape of GET /v1/overview?from&to[&unit_id] (sabha_api/services/overview.py). Every
// number comes with the count it is based on, so the page can hide a number whose underlying n is 0 instead of
// showing 0 or a placeholder (golden rule 6).

import type { ConversationType } from "../../design";

export interface TypeMedian {
  type: ConversationType;
  /** Median verified overall score, 1 to 5. */
  median: number;
  /** Recordings with an overall score in the period. */
  n: number;
}

export interface UnitMedian {
  unit_id: string;
  median: number;
  n: number;
}

export interface WeekMedian {
  from: string;
  /** null: no verified score that week. */
  median: number | null;
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
  /** The same median per top-level unit with scores, by unit name. */
  by_unit?: UnitMedian[];
  /** Eight weeks ending at the period's end, oldest first. */
  weekly?: WeekMedian[];
}

/** What is in the pipeline right now, by stage (GET /v1/overview `in_progress`; stages with none are left out). */
export interface StageCount {
  stage: "uploading" | "queued" | "preparing" | "finding_speakers" | "transcribing" | "analysing" | "needs_review";
  n: number;
}

export interface ProcessingItem {
  id: string;
  title: string;
  type: ConversationType;
  stage: StageCount["stage"];
  person_name: string | null;
}

export interface Turnaround {
  type: ConversationType;
  /** Median minutes from upload to finished report, last 30 days. */
  minutes: number;
  n: number;
}

/** One period's numbers. */
export interface PeriodStats {
  /** Period as UTC instants, [from, to). */
  from: string;
  to: string;
  recordings_analysed: number;
  audio_hours: number;
  /** Silence skipped, over the `silence_n` recordings whose speech time is known. */
  silence_hours?: number;
  silence_n?: number;
  median_overall_by_type: TypeMedian[];
  /** Reception calls with a ticket, and how many were resolved. */
  tickets?: number;
  tickets_resolved?: number;
}

export interface OverviewStats extends PeriodStats {
  unit_id?: string | null;
  /** Top-level units the caller may see: the campus switcher. */
  units?: { id: string; name: string }[];
  /** Eight periods of this length, oldest first; the last is this period, the one before it the previous. */
  series?: PeriodStats[];
  /** Lowest median verified dimension scores in the period, lowest first. */
  coaching: CoachingItem[];
  in_progress?: StageCount[];
  processing?: ProcessingItem[];
  turnaround?: Turnaround[];
}
