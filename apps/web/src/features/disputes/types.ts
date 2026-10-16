// Dispute and review payloads (P6.7). The API (P6.7 backend) will be built to match these shapes.

/** What the dialog sends: POST /v1/analyses/{id}/disputes. */
export interface DisputeDraft {
  dimension_key: string;
  /** Whole number from 1 to 5, different from the score shown. */
  proposed_score: number;
  comment: string;
}

export type DisputeStatus = "open" | "accepted" | "rejected";

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
      proposed_score: number;
      comment: string;
      evidence: { quote: string; start_ms: number }[];
      status: DisputeStatus;
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
