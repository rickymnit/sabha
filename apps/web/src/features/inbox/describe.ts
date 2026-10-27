// The words, icon and action for each kind of inbox item (GET /v1/inbox), shared by the bell and the Overview.

import type { InboxItem, Me } from "../../api/types";
import type { IconName } from "../../design";

export interface Described {
  icon: IconName;
  tone: string;
  title: string;
  detail: string;
  action: string;
  to: string;
}

const words = (code: string) => code.replace(/_/g, " ");
const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function describeInboxItem(item: InboxItem, labels: Me["tenant"]["labels"]): Described {
  const where = [item.recording_title, item.unit].filter(Boolean).join(", ");
  switch (item.kind) {
    case "dispute":
      return {
        icon: "message",
        tone: "bg-primary-tint text-primary",
        title: `${item.person_name ?? "Someone"} disputes a score`,
        detail: `${item.dimension_name ?? "A score"}, ${item.recording_title}: AI gave ${item.ai_score}, proposed ${item.proposed_score}`,
        action: "Decide",
        to: "/reviews?tab=disputes",
      };
    case "review":
      return item.reason === "unclear_roles"
        ? {
            icon: "people",
            tone: "bg-warning-tint text-warning",
            title: `Who is the ${labels.person.toLowerCase()}?`,
            detail: [where, item.note].filter(Boolean).join(": "),
            action: "Choose speaker",
            to: `/reviews/${item.recording_id}`,
          }
        : {
            icon: "reviews",
            tone: "bg-warning-tint text-warning",
            title: `${item.recording_title} needs a review`,
            detail: item.note ?? "",
            action: "Review",
            to: `/reviews/${item.recording_id}`,
          };
    case "failed":
      return {
        icon: "alert",
        tone: "bg-danger-tint text-danger",
        title: `${item.recording_title} could not be processed`,
        detail: item.note ?? "",
        action: "Retry or close",
        to: `/recordings/${item.recording_id}`,
      };
    case "follow_up":
      return {
        icon: "phone",
        tone: "bg-warning-tint text-warning",
        title: `${item.ticket_category ? sentence(words(item.ticket_category)) + " call" : "A call"} needs follow-up`,
        detail: [where, item.follow_up].filter(Boolean).join(": "),
        action: "View ticket",
        to: `/recordings/${item.recording_id}`,
      };
  }
}
