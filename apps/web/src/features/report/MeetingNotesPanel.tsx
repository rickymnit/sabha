// Meeting notes: what was decided, who does what by when, and what was left open. Every item is backed by a quote
// found in the transcript (sabha_analytics.meetings); its time button plays that moment. Owners are shown by the name
// people gave the voice, or as named in the meeting.

import { useId, type ReactNode } from "react";

import { Quote } from "./DealCardPanel";
import type { MeetingNotes } from "./types";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <h3 className="m-0 text-sm font-semibold uppercase tracking-wide text-muted-2">{title}</h3>
      {children}
    </div>
  );
}

export interface MeetingNotesPanelProps {
  notes: MeetingNotes;
  /** The display name of a voice ("Riya", or "Voice 2"). */
  voiceName: (voice: string) => string;
  onSeek: (ms: number) => void;
}

export function MeetingNotesPanel({ notes, voiceName, onSeek }: MeetingNotesPanelProps) {
  const headingId = useId();
  const owner = (item: MeetingNotes["action_items"][number]) =>
    item.owner_voice ? voiceName(item.owner_voice) : (item.owner ?? "Not named");
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-5 rounded-panel border border-line bg-surface px-6 py-5"
    >
      <h2 id={headingId} className="m-0 text-lg font-semibold">
        Meeting notes
      </h2>

      <Section title="Action items">
        {notes.action_items.length === 0 ? (
          <p className="m-0 rounded-card border border-warning-border bg-warning-surface px-4 py-3 text-ink-2">
            No work was given to anyone in this meeting.
          </p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {notes.action_items.map((item) => (
              <li
                key={item.evidence.utterance_id + item.action}
                className="grid gap-x-4 gap-y-1 rounded-card border border-line-subtle px-4 py-3 sm:grid-cols-[minmax(0,1fr)_160px_140px]"
              >
                <span className="font-semibold text-ink">{item.action}</span>
                <span className="text-small text-ink-2">
                  <span className="text-muted sm:hidden">Who: </span>
                  {owner(item)}
                </span>
                <span className="text-small text-ink-2">
                  <span className="text-muted sm:hidden">When: </span>
                  {item.due ?? <span className="text-warning-ink">No date said</span>}
                </span>
                <span className="sm:col-span-3">
                  <Quote evidence={item.evidence} onSeek={onSeek} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Decisions">
          {notes.decisions.length === 0 ? (
            <p className="m-0 text-muted">No decision was said out loud.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {notes.decisions.map((item) => (
                <li key={item.evidence.utterance_id + item.decision} className="flex flex-col gap-1">
                  <span className="text-ink">{item.decision}</span>
                  <Quote evidence={item.evidence} onSeek={onSeek} />
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Left open">
          {notes.open_questions.length === 0 ? (
            <p className="m-0 text-muted">Nothing was left open.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {notes.open_questions.map((item) => (
                <li key={item.evidence.utterance_id + item.question} className="flex flex-col gap-1">
                  <span className="text-ink">{item.question}</span>
                  <Quote evidence={item.evidence} onSeek={onSeek} />
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <p className="m-0 border-t border-track pt-3 text-caption text-muted">
        Every item is backed by words found in the transcript.
        {notes.left_out > 0 &&
          ` ${notes.left_out} ${notes.left_out === 1 ? "item was" : "items were"} left out because its words could not be found.`}
      </p>
    </section>
  );
}
