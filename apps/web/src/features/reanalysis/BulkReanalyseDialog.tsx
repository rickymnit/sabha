// Re-analyse many recordings at once (P2.8; owners and admins), for example after a rubric was updated. It first
// counts the finished recordings of the chosen type that were scored with another rubric, then starts at most 100
// per click; the rest can be started with another click.

import { useEffect, useId, useState, type FormEvent } from "react";

import type { BulkReanalysisRequest, BulkReanalysisResult } from "../../api/types";
import { Button, Dialog } from "../../design";

export interface BulkReanalyseDialogProps {
  types: readonly string[];
  /** The tenant's words for recordings, for example "lessons". */
  recordingsWord: string;
  typeLabel: (type: string) => string;
  run: (request: BulkReanalysisRequest) => Promise<BulkReanalysisResult>;
  onStarted: (result: BulkReanalysisResult) => void;
  onClose: () => void;
}

export function BulkReanalyseDialog({
  types,
  recordingsWord,
  typeLabel,
  run,
  onStarted,
  onClose,
}: BulkReanalyseDialogProps) {
  const typeId = useId();
  const reasonId = useId();
  const errorId = useId();
  const [type, setType] = useState(types[0] ?? "");
  const [reason, setReason] = useState("");
  const [count, setCount] = useState<BulkReanalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let current = true;
    run({ type, reason: "Counting before a re-analysis.", dry_run: true })
      .then((result) => current && setCount(result))
      .catch(() => current && setError("Could not count them. Please try again."));
    return () => {
      current = false;
    };
  }, [type, run]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError("Say why, for the record.");
    setError(null);
    setSending(true);
    try {
      onStarted(await run({ type, reason: reason.trim(), dry_run: false }));
      onClose();
    } catch {
      setError("It could not be started. Please try again.");
      setSending(false);
    }
  }

  const matching = count?.matching;
  const now = Math.min(matching ?? 0, 100);
  return (
    <Dialog
      title={`Re-analyse ${recordingsWord}`}
      description={
        <p className="m-0">
          After a rubric is updated, Sabha can score finished {recordingsWord} again from their transcripts. Earlier
          reports are kept as earlier versions. Nobody is emailed.
        </p>
      }
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={typeId} className="text-sm font-semibold">
            Type
          </label>
          <select
            id={typeId}
            value={type}
            onChange={(e) => {
              setCount(null);
              setType(e.target.value);
            }}
            className="min-h-touch rounded border border-line-input bg-surface px-3"
          >
            {types.map((t) => (
              <option key={t} value={t}>
                {typeLabel(t)}
              </option>
            ))}
          </select>
        </div>
        <p
          className="m-0 rounded-card border border-line-subtle bg-surface-subtle px-4 py-3 text-ink-2"
          aria-live="polite"
        >
          {matching === undefined
            ? "Counting…"
            : matching === 0
              ? `All finished ${typeLabel(type).toLowerCase()} ${recordingsWord} already use the current rubric.`
              : (matching === 1
                  ? "1 finished one was scored with an older rubric."
                  : `${matching} finished ${recordingsWord} were scored with an older rubric.`) +
                (matching > 100 ? ` The first 100 start now; run this again for the rest.` : "")}
        </p>
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
          <Button type="submit" disabled={sending || !now}>
            {sending ? "Starting…" : now ? `Re-analyse ${now}` : "Re-analyse"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
