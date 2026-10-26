// Dispute and review payloads (P6.7), as the API sends them (sabha_api.services.disputes).

/** What the dialog sends: POST /v1/analyses/{id}/disputes. */
export interface DisputeDraft {
  dimension_key: string;
  /** Whole number from 1 to 5, different from the score shown. */
  proposed_score: number;
  comment: string;
}

/** "closed": the recording was re-analysed before anyone decided. */
export type DisputeStatus = "open" | "accepted" | "rejected" | "closed";

/** One item in the reviewer's queue: GET /v1/reviews. */
export type ReviewItem =
  | {
      kind: "dispute";
      id: string;
      recording_id: string;
      recording_title: string;
      person_name: string;
      unit: string;
      dimension_key: string;
      dimension_name: string;
      ai_score: number;
      /** The score shown when the dispute was raised: a reviewer's, after an earlier accepted dispute. */
      current_score?: number;
      proposed_score: number;
      comment: string;
      evidence: { quote: string; start_ms: number }[];
      status: DisputeStatus;
      /** The viewer raised it, so someone else decides it. */
      raised_by_me?: boolean;
      /** ISO 8601 UTC. */
      created_at: string;
    }
  | {
      kind: "needs_review";
      id: string;
      recording_id: string;
      recording_title: string;
      person_name: string;
      unit: string;
      reason: string;
      status: "open" | "resolved";
      created_at: string;
    };

/** POST /v1/disputes/{id}/resolve. */
export interface Resolution {
  decision: "accepted" | "rejected";
  /** Required when accepted. */
  final_score?: number;
  note: string;
}

export const COMMENT_MIN = 10;
export const COMMENT_MAX = 500;

/** GET /v1/disputes. */
export interface DisputePage {
  items: Extract<ReviewItem, { kind: "dispute" }>[];
  next_cursor: string | null;
}
