// Mapping API responses to the report components' props (pages/RecordingPage.tsx).

import type { RecordingDetail } from "../api/types";
import type { ReportRecording } from "../features/report/types";
import type { RoleLabels, Transcript } from "../features/transcript";
import { capitalise } from "../app/format";

/** The roles in a transcript, labelled in the tenant's words: the analysed staff role gets labels.person. */
export function roleLabels(roles: Record<string, string>, personLabel: string): RoleLabels {
  const staff = new Set(["teacher", "receptionist", "sales_rep"]);
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

/** "Riya", or "Voice 2" for the second voice heard when nobody has named it. */
export function voiceLabel(voice: string, order: readonly string[], names: Record<string, string>): string {
  return names[voice] ?? `Voice ${order.indexOf(voice) + 1}`;
}

/**
 * Meetings: every line is a "participant", so the transcript and timeline show each voice instead, by the name
 * people gave it. Returns the transcript with each line's role set to its voice, the labels for those voices, and
 * the voices in order of first speech.
 */
export function meetingView(
  transcript: Transcript,
  names: Record<string, string>,
): { transcript: Transcript; roles: RoleLabels; voices: string[] } {
  const voices = [...new Set(transcript.utterances.map((u) => u.speaker_label))];
  const roles: Record<string, { label: string; analysed?: boolean }> = {};
  for (const voice of voices) roles[voice] = { label: voiceLabel(voice, voices, names) };
  return {
    transcript: { ...transcript, utterances: transcript.utterances.map((u) => ({ ...u, role: u.speaker_label })) },
    roles,
    voices,
  };
}
