// Dispute dialog on the report (P6.7): the person analysed or their manager asks a reviewer to look at one score.
// Accessible modal: labelled by its heading, focus moves in on open and back to the trigger on close, Escape closes,
// and Tab stays inside.

import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "../../design";
import { COMMENT_MAX, COMMENT_MIN, type DisputeDraft } from "./types";

export interface DisputableDimension {
  key: string;
  name: string;
  /** The score currently shown (the reviewer's if there is one). */
  score: number;
}

export interface DisputeDialogProps {
  open: boolean;
  dimensions: readonly DisputableDimension[];
  initialKey?: string;
  onSubmit: (draft: DisputeDraft) => Promise<void>;
  onClose: () => void;
}

const SCORES = [1, 2, 3, 4, 5];

export function DisputeDialog({ open, ...props }: DisputeDialogProps) {
  // Mounting the body on each open gives a fresh, empty form without resetting state in an effect.
  return open ? <DialogBody {...props} /> : null;
}

function DialogBody({ dimensions, initialKey, onSubmit, onClose }: Omit<DisputeDialogProps, "open">) {
  const titleId = useId();
  const errorId = useId();
  const commentId = useId();
  const countId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<Element | null>(null);
  const [key, setKey] = useState(initialKey ?? dimensions[0]?.key ?? "");
  const [proposed, setProposed] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    returnFocus.current = document.activeElement;
    dialogRef.current?.querySelector<HTMLElement>("select, input, textarea, button")?.focus();
    return () => {
      if (returnFocus.current instanceof HTMLElement) returnFocus.current.focus();
    };
  }, []);

  const current = dimensions.find((d) => d.key === key);

  function trapFocus(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = [
      ...dialogRef.current.querySelectorAll<HTMLElement>("select, input, textarea, button:not([disabled])"),
    ];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = comment.trim();
    if (!current) return setError("Choose the score you want reviewed.");
    if (proposed === null) return setError("Choose the score you think is right.");
    if (proposed === current.score) return setError(`The score is already ${current.score}; choose a different one.`);
    if (text.length < COMMENT_MIN) return setError(`Explain why in at least ${COMMENT_MIN} characters.`);
    setError(null);
    setSending(true);
    try {
      await onSubmit({ dimension_key: current.key, proposed_score: proposed, comment: text });
      onClose();
    } catch {
      setError("The dispute could not be sent. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={trapFocus}
        className="flex w-full max-w-[520px] flex-col gap-4 rounded-panel border border-line bg-surface p-6"
      >
        <h2 id={titleId} className="m-0 text-xl font-semibold">
          Dispute a score
        </h2>
        <p className="m-0 text-sm text-muted">
          A reviewer will read your reason, look at the evidence and either change the score or explain why it stays.
          The AI score is kept in the history either way.
        </p>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm font-semibold">
            Score to review
            <select
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="min-h-touch rounded border border-line-input bg-surface px-3 font-normal"
            >
              {dimensions.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.name} (now {d.score})
                </option>
              ))}
            </select>
          </label>
          <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
            <legend className="mb-1.5 p-0 text-sm font-semibold">The score you think is right</legend>
            <div className="flex gap-2">
              {SCORES.map((s) => (
                <label
                  key={s}
                  className="flex min-h-touch min-w-touch cursor-pointer items-center justify-center gap-1.5 rounded border border-line-input px-3 has-[:checked]:border-primary has-[:checked]:bg-primary-tint"
                >
                  <input
                    type="radio"
                    name="proposed"
                    value={s}
                    checked={proposed === s}
                    onChange={() => setProposed(s)}
                    disabled={current?.score === s}
                  />
                  {s}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={commentId} className="text-sm font-semibold">
              Why
            </label>
            <textarea
              id={commentId}
              value={comment}
              onChange={(e) => setComment(e.target.value.slice(0, COMMENT_MAX))}
              rows={4}
              aria-describedby={error ? `${countId} ${errorId}` : countId}
              className="rounded border border-line-input bg-surface p-3"
            />
            <span id={countId} className="text-caption text-muted">
              {comment.length} of {COMMENT_MAX} characters
            </span>
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
              {sending ? "Sending…" : "Send dispute"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
