// Asks why before an owner or admin retries or closes a failed recording (P7.8); the reason goes to the audit log.

import { useId, useState, type FormEvent, type ReactNode } from "react";

import { Button, Dialog } from "../../design";

export interface ReasonDialogProps {
  title: string;
  description: ReactNode;
  submitLabel: string;
  onSubmit: (reason: string) => Promise<void>;
  onClose: () => void;
}

export function ReasonDialog({ title, description, submitLabel, onSubmit, onClose }: ReasonDialogProps) {
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
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "It did not work. Please try again.");
      setSending(false);
    }
  }

  return (
    <Dialog title={title} description={<p className="m-0">{description}</p>} onClose={onClose}>
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
            {sending ? "Working…" : submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
