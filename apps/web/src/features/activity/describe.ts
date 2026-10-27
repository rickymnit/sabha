// Audit entries in plain words for the Activity page (P1.8): "played the audio of Fractions, Class 7B". Nouns come
// from the tenant's labels; an action this version does not know is still shown, by its code.

import type { AuditEntryItem, Me } from "../../api/types";
import { TYPE_INFO } from "../../app/conversationTypes";
import type { ConversationType } from "../../design";

type Labels = Me["tenant"]["labels"];

/** The sentence after the actor's name, split so the page can link the target. */
export interface Description {
  /** Words before the target, for example "played the audio of". */
  text: string;
  /** The recording's title or the person's name, when the entry has one. */
  target: string | null;
  /** Anything after the target, for example ` as Reviewer`. */
  after?: string;
  /** Where the target opens, when it is a recording. */
  href?: string;
}

/** The actions the filter offers, with what the page calls them. */
export function actionChoices(labels: Labels): { value: string; label: string }[] {
  const thing = labels.recording.toLowerCase();
  return [
    { value: "recording.play", label: "Played audio" },
    { value: "analysis.view", label: "Opened reports" },
    { value: "recording.create", label: `Uploaded ${labels.recording_plural.toLowerCase()}` },
    { value: "dispute.create", label: "Disputed scores" },
    { value: "dispute.resolve", label: "Decided disputes" },
    { value: "recording.review", label: `Reviewed ${labels.recording_plural.toLowerCase()}` },
    { value: "recording.reanalyze", label: `Re-analysed a ${thing}` },
    { value: "settings.update", label: "Changed settings" },
    { value: "user.invite", label: "Invited people" },
  ];
}

const ROLE_WORDS: Record<string, (labels: Labels) => string> = {
  owner: () => "Owner",
  admin: () => "Administrator",
  manager: (labels) => labels.manager,
  reviewer: () => "Reviewer",
  staff: (labels) => labels.person,
};

export function roleWord(role: string, labels: Labels): string {
  return ROLE_WORDS[role]?.(labels) ?? role;
}

const quoted = (value: unknown) => `“${String(value)}”`;

/** What a settings change did, from its before and after (services/settings.py). */
function settingsChange(meta: Record<string, unknown>): string {
  const before = (meta.before ?? {}) as Record<string, unknown>;
  const after = (meta.after ?? {}) as Record<string, unknown>;
  const parts: string[] = [];
  if (typeof after.name === "string") parts.push(`renamed the organisation to ${quoted(after.name)}`);
  const words = (after.labels ?? {}) as Record<string, string>;
  const old = (before.labels ?? {}) as Record<string, string>;
  for (const [key, value] of Object.entries(words)) {
    parts.push(`changed the word ${quoted(old[key] ?? key)} to ${quoted(value)}`);
  }
  if (Array.isArray(after.enabled_types)) {
    const names = (after.enabled_types as ConversationType[]).map((t) => TYPE_INFO[t]?.name ?? t);
    parts.push(`set the conversation types to ${names.join(", ")}`);
  }
  return parts.length ? parts.join("; ") : "changed the settings";
}

export function describe(entry: AuditEntryItem, labels: Labels): Description {
  const thing = labels.recording.toLowerCase();
  const recording = entry.target.label;
  const href = entry.target.type === "recording" ? `/recordings/${encodeURIComponent(entry.target.id)}` : undefined;
  const onRecording = (text: string): Description => ({
    text,
    target: recording ?? `a ${thing} that no longer exists`,
    ...(recording && href ? { href } : {}),
  });
  switch (entry.action) {
    case "recording.play":
      return onRecording("played the audio of");
    case "analysis.view":
      return onRecording("opened the report for");
    case "recording.create":
      return onRecording("uploaded");
    case "recording.reanalyze":
      return onRecording("re-analysed");
    case "recording.review":
      return onRecording("reviewed");
    case "recording.voices":
      return onRecording("named the voices in");
    case "dispute.create":
      return { text: "disputed a score on", target: recording ?? `a ${thing}` };
    case "dispute.resolve":
      return { text: "decided a dispute on", target: recording ?? `a ${thing}` };
    case "settings.update":
      return { text: settingsChange(entry.meta), target: null };
    case "user.invite": {
      const role = typeof entry.meta.role === "string" ? roleWord(entry.meta.role, labels) : null;
      return {
        text: "invited",
        target: entry.target.label ?? "someone",
        ...(role ? { after: ` as ${/^[aeiou]/i.test(role) ? "an" : "a"} ${role.toLowerCase()}` } : {}),
      };
    }
    default:
      return { text: entry.action.replaceAll(".", " ").replaceAll("_", " "), target: entry.target.label };
  }
}
