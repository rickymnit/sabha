// Re-analyse one recording (P2.8; owners and admins): Sabha scores it again from its transcript with the current
// rubric. The current report stays as an earlier version; open disputes about it are closed.

import { useId, useState, type FormEvent } from "react";

import { Button, Dialog } from "../../design";

export interface ReanalyseDialogProps {
  /** The tenant's word for a recording, for example "lesson". */
  recordingWord: string;
  onSubmit: (reason: string) => Promise<void>;
  onClose: () => void;
}

export function ReanalyseDialog({ recordingWord, onSubmit, onClose }: ReanalyseDialogProps) {
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
      await onSubmit(reason.trim());
      onClose();
    } catch {
      setError("It could not be started. Please try again.");
      setSending(false);
    }
  }

  return (
    <Dialog
      title={`Re-analyse this ${recordingWord}`}
      description={
        <p className="m-0">
          Sabha scores it again from its transcript with the current rubric, in a few minutes. The current report is
          kept as an earlier version, and any open disputes about it are closed. Nobody is emailed.
        </p>
      }
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
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
