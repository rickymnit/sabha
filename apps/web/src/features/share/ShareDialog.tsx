// Share reports with the people analysed (UI v2 "Share with Anjali", "Share with staff"; owner's decision
// 2026-11-03): each person gets an email with a link and sees the note on their report. Sharing does not change who
// may see a report.

import { useId, useState, type FormEvent } from "react";

import { Button, Dialog } from "../../design";

export interface ShareDialogProps {
  /** "Anjali" for one report, "3 staff" for several. */
  who: string;
  /** The tenant's word for one report's recording, for example "lesson". */
  recordingWord: string;
  count: number;
  onSubmit: (note: string | null) => Promise<void>;
  onClose: () => void;
}

const MAX_NOTE = 500;

export function ShareDialog({ who, recordingWord, count, onSubmit, onClose }: ShareDialogProps) {
  const noteId = useId();
  const errorId = useId();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSending(true);
    try {
      await onSubmit(note.trim() || null);
      onClose();
    } catch {
      setError("It could not be shared. Please try again.");
      setSending(false);
    }
  }

  const reports = count === 1 ? `this ${recordingWord} report` : `${count} ${recordingWord} reports`;
  return (
    <Dialog
      title={`Share with ${who}`}
      description={
        <p className="m-0">
          {count === 1 ? `${who} gets` : "Each person gets"} an email with a link to {reports}, and sees your note at
          the top. Strengths are shown first. Who can see the report does not change.
        </p>
      }
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={noteId} className="text-sm font-semibold">
            Note <span className="font-normal text-muted">(optional)</span>
          </label>
          <textarea
            id={noteId}
            value={note}
            onChange={(e) => setNote(e.target.value.slice(0, MAX_NOTE))}
            rows={3}
            placeholder="What went well, and what to look at together"
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
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={sending}>
            {sending ? "Sharing…" : "Share"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
