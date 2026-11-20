// Re-analyse one recording (P2.8; owners and admins): Sabha scores it again from its transcript with the current
// rubric, or (one recording with its audio, ADR 0018) transcribes it again with other speech models first. The
// current report stays as an earlier version; open disputes about it are closed.

import { useId, useState, type FormEvent } from "react";

import type { SpeechModel } from "../../api/types";
import { Button, Dialog, SegmentedControl } from "../../design";
import { rememberedModel, speechFields, type SpeechValue } from "../speech/models";
import { SpeechChoices } from "../speech/SpeechChoices";

/** Transcribing again (ADR 0018): offered for one recording whose audio is still kept. */
export interface SpeechRedoOption {
  /** What the current transcript was made with. */
  initial: SpeechValue;
  /** Owners and admins choose the transcription model; leave out while loading. */
  models?: readonly SpeechModel[];
  /** A support call: ask whether a colleague helped. */
  support: boolean;
  /** The tenant's word for the person analysed, lower case. */
  personWord: string;
}

export interface ReanalyseDialogProps {
  /** The tenant's word for a recording, for example "lesson". */
  recordingWord: string;
  /** Several chosen on the Recordings page: how many, and the plural word. */
  count?: number;
  recordingsWord?: string;
  /** The rubric they will be scored with, for example "v1.3". */
  version?: string;
  /** Offer "Transcribe again with other models"; leave out for scores only. */
  speech?: SpeechRedoOption;
  onSubmit: (reason: string, speech?: Record<string, unknown>) => Promise<void>;
  onClose: () => void;
}

export function ReanalyseDialog({
  recordingWord,
  count = 1,
  recordingsWord,
  version,
  speech,
  onSubmit,
  onClose,
}: ReanalyseDialogProps) {
  const [mode, setMode] = useState<"scores" | "speech">("scores");
  const [choice, setChoice] = useState<SpeechValue | null>(null);
  const models = speech?.models;
  const current = choice ?? speech?.initial;
  // The model the transcript was made with, else the one last chosen on this device.
  const value = current && {
    ...current,
    asrModel: current.asrModel || (models ? rememberedModel(models) : ""),
  };
  const redo = mode === "speech" && speech && value;
  const reasonId = useId();
  const errorId = useId();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError("Say why, for the record.");
    setError(null);
    setSending(true);
    try {
      await onSubmit(reason.trim(), redo ? speechFields(value, speech.support, Boolean(models)) : undefined);
      onClose();
    } catch {
      setError("It could not be started. Please try again.");
      setSending(false);
    }
  }

  return (
    <Dialog
      title={count === 1 ? `Re-analyse this ${recordingWord}` : `Re-analyse ${count} ${recordingsWord ?? "recordings"}`}
      description={
        <p className="m-0">
          {redo ? (
            <>
              Sabha transcribes it again with the models below, then scores it with the current rubric
              {version ? ` (${version})` : ""}. This pays for speech-to-text again and takes about as long as the first
              time. The current report is kept as an earlier version, and any open disputes about it are closed.
            </>
          ) : (
            <>
              Sabha scores {count === 1 ? "it" : "each one"} again from the transcript with the current rubric
              {version ? ` (${version})` : ""}, in a few minutes. The current report is kept as an earlier version, and
              any open disputes about it are closed. Nobody is emailed, and it does not use this month&apos;s audio
              hours.
            </>
          )}
        </p>
      }
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {speech && (
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-ink">What to redo</span>
            <SegmentedControl<"scores" | "speech">
              label="What to redo"
              value={mode}
              onChange={setMode}
              options={[
                { value: "scores", label: "Scores only" },
                { value: "speech", label: "Transcribe again with other models" },
              ]}
            />
          </div>
        )}
        {redo && (
          <SpeechChoices
            value={value}
            onChange={setChoice}
            models={models}
            support={speech.support}
            personWord={speech.personWord}
          />
        )}
        <div className="flex flex-col gap-1.5">
          <label htmlFor={reasonId} className="text-sm font-semibold">
            Why
          </label>
          <textarea
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value.slice(0, 500))}
            rows={3}
            aria-describedby={error ? errorId : undefined}
            className="rounded border border-line-input bg-surface p-3"
          />
        </div>
        {error && (
          <p id={errorId} role="alert" className="m-0 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={sending}>
            {sending ? "Starting…" : "Re-analyse"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
