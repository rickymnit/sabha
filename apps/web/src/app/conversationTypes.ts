// Display names and descriptions of the conversation types, from the setup design (Setup.dc.html:171-177). Shared by
// the Settings and Rubrics pages.

import type { ConversationType } from "../design";

/** The setup screen's names and descriptions for each conversation type (Setup.dc.html:171-177). */
export const TYPE_INFO: Record<ConversationType, { name: string; description: string }> = {
  teaching: { name: "Teaching", description: "Lessons, lectures and training: clarity, questioning, pacing" },
  counselling: { name: "Counselling", description: "One-to-one sessions: empathy, cause, agreed plan" },
  reception: { name: "Reception", description: "Front-desk calls and visits: intent, accuracy, resolution" },
  meeting: { name: "Meetings", description: "Internal meetings: decisions, owners, open issues" },
  sales: { name: "Sales", description: "Sales meetings and calls: discovery, objections, next step" },
};
