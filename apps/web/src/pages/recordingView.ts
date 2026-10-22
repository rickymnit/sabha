// Mapping API responses to the report components' props (pages/RecordingPage.tsx).

import type { RecordingDetail } from "../api/types";
import type { ReportRecording } from "../features/report/types";
import type { RoleLabels } from "../features/transcript";
import { capitalise } from "../app/format";

/** The roles in a transcript, labelled in the tenant's words: the analysed staff role gets labels.person. */
export function roleLabels(roles: Record<string, string>, personLabel: string): RoleLabels {
  const staff = new Set(["teacher", "receptionist"]);
  const out: Record<string, { label: string; analysed?: boolean }> = {};
  for (const role of new Set(Object.values(roles))) {
    out[role] = staff.has(role) ? { label: personLabel, analysed: true } : { label: capitalise(role) };
  }
  return out;
}

export function reportRecording(detail: RecordingDetail): ReportRecording {
  return {
    id: detail.id,
    title: detail.title,
    type_label: detail.type_label,
    person: { id: detail.person?.id ?? "", name: detail.person?.name ?? "—", unit: detail.unit_name ?? "" },
    recorded_at: detail.recorded_at,
    duration_ms: detail.duration_ms ?? 0,
    speech_ms: detail.speech_ms,
    languages: detail.languages,
    removed_silence: detail.removed_silence,
  };
}
