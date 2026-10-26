// Meetings: who spoke how much, with a box to name each voice. Voices are the diarizer's anonymous labels; names are
// for display only (stored on the recording, never sent to a model, never used to score anyone).

import { useId, useState, type FormEvent } from "react";

import { Button, Input } from "../../design";
import type { Transcript } from "../transcript";
import { formatPercent } from "./format";

export interface VoicesPanelProps {
  transcript: Transcript;
  /** Voices in order of first speech. */
  voices: string[];
  names: Record<string, string>;
  onSave: (names: Record<string, string>) => Promise<void>;
}

export function VoicesPanel({ transcript, voices, names, onSave }: VoicesPanelProps) {
  const headingId = useId();
  const [draft, setDraft] = useState<Record<string, string>>(names);
  const [saving, setSaving] = useState(false);
  const talk = new Map<string, number>();
  for (const u of transcript.utterances)
    talk.set(u.speaker_label, (talk.get(u.speaker_label) ?? 0) + u.end_ms - u.start_ms);
  const total = [...talk.values()].reduce((a, b) => a + b, 0) || 1;
  const changed = voices.some((v) => (draft[v] ?? "").trim() !== (names[v] ?? ""));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave(Object.fromEntries(voices.map((v) => [v, (draft[v] ?? "").trim()])));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-4 rounded-panel border border-line bg-surface px-6 py-5"
    >
      <div className="flex flex-col gap-1">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          Who spoke
        </h2>
        <p className="m-0 text-sm text-muted">
          Name the voices so the notes and transcript show who said what. Nobody is scored.
        </p>
      </div>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {voices.map((voice, index) => {
            const share = (talk.get(voice) ?? 0) / total;
            return (
              <li key={voice} className="flex flex-col gap-1.5 rounded-card border border-line-subtle px-3.5 py-3">
                <span className="flex items-baseline justify-between text-small text-muted">
                  <span>Voice {index + 1}</span>
                  <span>{formatPercent(share)} of the talk</span>
                </span>
                <span aria-hidden="true" className="block h-1.5 overflow-hidden rounded-full bg-track">
                  <span
                    className="block h-1.5 rounded-full bg-primary"
                    style={{ width: `${Math.round(share * 100)}%` }}
                  />
                </span>
                <Input
                  label={`Name of voice ${index + 1}`}
                  hideLabel
                  placeholder="Name"
                  maxLength={40}
                  value={draft[voice] ?? ""}
                  onChange={(e) => setDraft({ ...draft, [voice]: e.target.value })}
                />
              </li>
            );
          })}
        </ul>
        <div>
          <Button type="submit" variant="secondary" disabled={!changed || saving}>
            {saving ? "Saving…" : "Save names"}
          </Button>
        </div>
      </form>
    </section>
  );
}
