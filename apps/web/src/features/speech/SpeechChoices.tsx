// The speech choices of an upload (ADR 0012, 0014, 0015), shared by Upload, a phone call's Analyse and a single
// re-analysis (ADR 0017, 0018): the transcription model (owners and admins), how many speakers, how they are told
// apart, and for support calls whether a colleague helped.

import type { SpeechModel } from "../../api/types";
import { Select } from "../../design";
import { modelLabel, rememberModel, type SpeechValue } from "./models";

export interface SpeechChoicesProps {
  value: SpeechValue;
  onChange: (value: SpeechValue) => void;
  /** The models an owner or admin may choose; leave out to hide the choice (everyone else gets the usual one). */
  models?: readonly SpeechModel[];
  /** Show "Did a colleague help?" (support calls). */
  support: boolean;
  /** The tenant's word for the person analysed, lower case ("agent", "team member"). */
  personWord: string;
  disabled?: boolean;
}

export function SpeechChoices({ value, onChange, models, support, personWord, disabled }: SpeechChoicesProps) {
  const set = (change: Partial<SpeechValue>) => onChange({ ...value, ...change });
  const helped = support && value.transferred;
  const speakers = helped ? "3" : value.speakers;
  return (
    <div className="flex flex-col gap-4">
      {models && models.length > 0 && (
        <Select
          label="Transcription model"
          value={value.asrModel}
          disabled={disabled}
          onChange={(e) => {
            set({ asrModel: e.target.value });
            rememberModel(e.target.value);
          }}
          hint={`Turns speech into text. Usually ${models.find((m) => m.default)?.name ?? "the default"}.`}
        >
          {models.map((m) => (
            <option key={m.id} value={m.id} disabled={!m.available}>
              {modelLabel(m)}
            </option>
          ))}
        </Select>
      )}
      {support && value.supportCall && (
        <Select
          label="Who called?"
          value={value.supportCall}
          disabled={disabled}
          onChange={(e) =>
            set({ supportCall: e.target.value === "ticket_callback" ? "ticket_callback" : "customer_called" })
          }
          hint={
            value.supportCall === "ticket_callback"
              ? "The problem is known from the ticket, so it is judged on following it up and closing it."
              : "The customer rang with a problem."
          }
        >
          <option value="customer_called">The customer called support</option>
          <option value="ticket_callback">Support called back about a ticket</option>
        </Select>
      )}
      {support && (
        <Select
          label="Did a colleague help on this call?"
          value={value.transferred ? "yes" : "no"}
          disabled={disabled}
          onChange={(e) => set({ transferred: e.target.value === "yes" })}
          hint={
            value.transferred
              ? `Every score still goes to the ${personWord}; the colleague's words count as theirs.`
              : undefined
          }
        >
          <option value="no">No</option>
          <option value="yes">Yes, a colleague helped</option>
        </Select>
      )}
      <Select
        label="Number of speakers"
        value={speakers}
        disabled={disabled || helped}
        onChange={(e) => set({ speakers: e.target.value })}
        hint={
          helped
            ? "A call a colleague helped on has 3: the agent, the colleague and the customer."
            : speakers === "2" && support
              ? `One is the ${personWord} and the other is the customer.`
              : "Count every voice in the recording. Automatic lets Sabha decide."
        }
      >
        <option value="auto">Automatic</option>
        {[2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
          <option key={n} value={String(n)}>
            {n}
          </option>
        ))}
      </Select>
      <Select
        label="Telling the speakers apart"
        value={value.speakerModel}
        disabled={disabled}
        onChange={(e) => set({ speakerModel: e.target.value === "gemini" ? "gemini" : "pyannote" })}
        hint={
          value.speakerModel === "gemini"
            ? "Gemini listens again and fixes who said which line. Adds about ₹9–11 per hour of audio."
            : "Sabha separates the voices by how they sound."
        }
      >
        <option value="pyannote">Standard (pyannote)</option>
        <option value="gemini">Standard + Gemini check</option>
      </Select>
    </div>
  );
}
