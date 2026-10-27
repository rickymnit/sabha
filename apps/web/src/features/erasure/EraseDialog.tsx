// Erasing one recording or one person (P7.3; owners only): first shows what would be erased (a count, nothing
// deleted), then asks why and for the name to be typed before anything is deleted. Deletion cannot be undone.

import { useEffect, useId, useState, type FormEvent } from "react";

import { Button, Dialog } from "../../design";

export interface ErasureResult {
  erased: boolean;
  recordings: number;
  files: number;
}

export interface EraseDialogProps {
  /** What is erased, in words: "this lesson", "all of Asha Rao's data". */
  what: string;
  /** The name the owner types to confirm. */
  confirmName: string;
  recordingWord: string;
  recordingsWord: string;
  run: (confirm: boolean, reason: string) => Promise<ErasureResult>;
  onErased: () => void;
  onClose: () => void;
}

export function EraseDialog({
  what,
  confirmName,
  recordingWord,
  recordingsWord,
  run,
  onErased,
  onClose,
}: EraseDialogProps) {
  const reasonId = useId();
  const nameId = useId();
  const [count, setCount] = useState<ErasureResult | null>(null);
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  // Count once when the dialog opens: `run` is a new function on every render of the page, so keep the first.
  const [countOnce] = useState(() => run);
  useEffect(() => {
    let current = true;
    countOnce(false, "Counting before erasure.")
      .then((result) => current && setCount(result))
      .catch(() => current && setError("Could not count what would be erased. Please try again."));
    return () => {
      current = false;
    };
  }, [countOnce]);

  const matches = typed.trim() === confirmName.trim();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError("Say why, for the record.");
    if (!matches) return setError(`Type ${confirmName} exactly to confirm.`);
    setError(null);
    setSending(true);
    try {
      await run(true, reason.trim());
      onErased();
    } catch {
      setError("It could not be erased. Please try again.");
      setSending(false);
    }
  }

  const n = count?.recordings ?? 0;
  return (
    <Dialog
      title={`Erase ${what}`}
      description={
        <p className="m-0">
          {count
            ? `This deletes ${n} ${n === 1 ? recordingWord : recordingsWord} with their audio, transcripts, scores, disputes and reports (${count.files} stored files). It cannot be undone. A record that the erasure happened, with your reason, is kept in Activity.`
            : "Counting what would be erased…"}
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
            rows={2}
            className="rounded border border-line-input bg-surface p-3"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={nameId} className="text-sm font-semibold">
            Type <span className="font-bold">{confirmName}</span> to confirm
          </label>
          <input
            id={nameId}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            className="min-h-touch rounded border border-line-input bg-surface px-3"
          />
        </div>
        {error && (
          <p role="alert" className="m-0 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={sending || !count || !matches} className="bg-danger hover:bg-danger">
            {sending ? "Erasing…" : "Erase for good"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
