// Fictional review queue for the /dev/reviews demo and tests: every name, school and line is made up.

import type { ReviewItem } from "../disputes/types";

export function mockReviewItems(): ReviewItem[] {
  return [
    {
      kind: "dispute",
      id: "dsp_001",
      recording_id: "rec_101",
      recording_title: "Class 8 Science: Photosynthesis",
      person_name: "Anjali Sharma",
      unit: "Main campus",
      dimension_key: "checks_for_understanding",
      dimension_name: "Checks for understanding",
      ai_score: 2,
      proposed_score: 3,
      comment: "I asked three students to explain the idea back, around 12 and 31 minutes.",
      evidence: [{ quote: "Sab samajh aa gaya na? Good.", start_ms: 731_000 }],
      status: "open",
      created_at: "2026-10-15T05:12:00Z",
    },
    {
      kind: "needs_review",
      id: "nr_002",
      recording_id: "rec_102",
      recording_title: "Fee concession follow-up",
      person_name: "Front desk",
      unit: "Mansarovar",
      reason: "unclear_roles",
      status: "open",
      created_at: "2026-10-15T04:40:00Z",
    },
    {
      kind: "dispute",
      id: "dsp_003",
      recording_id: "rec_103",
      recording_title: "Class 10 Maths: Quadratic equations",
      person_name: "Rohit Meena",
      unit: "Vaishali Nagar",
      dimension_key: "pacing",
      dimension_name: "Pacing",
      ai_score: 3,
      proposed_score: 4,
      comment: "The last ten minutes were planned revision, not rushing.",
      evidence: [{ quote: "Time kam hai, baaki chapter fatafat khatam karte hain.", start_ms: 2_410_000 }],
      status: "rejected",
      created_at: "2026-10-14T09:02:00Z",
    },
  ];
}
