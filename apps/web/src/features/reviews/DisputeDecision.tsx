// Right column of the Reviews page for a score dispute (docs/design/v2/05-reviews.png): the AI score with its
// reasoning beside the proposed score with the reason given (and a play button when the reason names a time), the
// quotes the AI used, then the decision. Accepting the proposed score needs no note; keeping the score or setting
// another one does, because the person reads why. Accepting replaces the AI score in the report and trends, the AI
// score stays as history, and the decision joins the calibration set (services/disputes.py).

import { useId, useState } from "react";

import { formatWhen } from "../../app/format";
import { Button, Icon, cx, scoreBand } from "../../design";
import type { Resolution } from "../disputes/types";
import { SmallPlayIcon } from "../report/icons";
import { formatClock } from "../transcript/text";
import { timeInText, type DisputeEntry } from "./queue";
import type { SamplePlayer } from "./useSamplePlayer";

const SCORE_INK = { low: "text-danger", mid: "text-warning-ink", good: "text-success" } as const;

export interface DisputeDecisionProps {
  item: DisputeEntry;
  /** The AI's reasoning for this score, from the report; shown under the AI score when known. */
  rationale?: string | null;
  player: SamplePlayer;
  recordingHref: string;
  onOpenRecording?: () => void;
  onResolve: (resolution: Resolution) => Promise<void>;
}

function TimeButton({ ms, player, label, word }: { ms: number; player: SamplePlayer; label: string; word?: string }) {
  const playing = player.playing === ms;
  return (
    <Button
      variant="secondary"
      aria-label={`${playing ? "Stop" : "Play"} ${label} at ${formatClock(ms)}`}
      onClick={() => void player.play(ms, ms + 15_000)}
      className="min-h-[36px] shrink-0 gap-1.5 px-2.5 text-small font-semibold tabular-nums"
    >
      {playing ? <Icon name="close" size={12} /> : <SmallPlayIcon />}
      {word && <span aria-hidden="true">{word}</span>}
      {formatClock(ms)}
    </Button>
  );
}

export function DisputeDecision({
  item,
  rationale,
  player,
  recordingHref,
  onOpenRecording,
  onResolve,
}: DisputeDecisionProps) {
  const headingId = useId();
  const noteId = useId();
  const errorId = useId();
  const [note, setNote] = useState("");
  const [choosing, setChoosing] = useState(false);
  const [other, setOther] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const shown = item.current_score ?? item.ai_score;
  const reviewed = shown !== item.ai_score;
  const raiser = item.raised_by_name ?? item.person_name ?? "Someone";
  const firstName = raiser.split(" ")[0] ?? raiser;
  const spokenAt = timeInText(item.comment);
  const otherScores = [1, 2, 3, 4, 5].filter((s) => s !== shown && s !== item.proposed_score);
  const hasNote = note.trim() !== "";
  const where = [
    item.person_name,
    item.unit,
    item.recorded_at && `recorded ${formatWhen(item.recorded_at).replace(/^[TY]/, (c) => c.toLowerCase())}`,
  ]
    .filter(Boolean)
    .join(", ");

  async function decide(resolution: Resolution) {
    if (resolution.decision === "rejected" || resolution.final_score !== item.proposed_score) {
      if (!hasNote) return setError(`Add a note: ${firstName} reads why.`);
    }
    setError(null);
    setSending(true);
    try {
      await onResolve(hasNote ? { ...resolution, note: note.trim() } : resolution);
    } catch (caught) {
      const code = caught instanceof Error && "code" in caught ? caught.code : null;
      setError(
        code === "own_dispute"
          ? "You raised this dispute, so someone else decides it."
          : code === "dispute_closed"
            ? "Someone else decided this dispute first."
            : "The decision could not be saved. Please try again.",
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col gap-5 rounded-panel border border-line bg-surface px-5 py-5 sm:px-6"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-small text-muted">Score dispute</span>
          <h2 id={headingId} className="m-0 text-2xl font-semibold tracking-tight">
            {item.dimension_name}: {item.recording_title}
          </h2>
          {where && <p className="m-0 text-sm text-ink-2">{where}</p>}
        </div>
        <a
          href={recordingHref}
          onClick={(e) => {
            if (!onOpenRecording || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
            e.preventDefault();
            onOpenRecording();
          }}
          className="inline-flex min-h-touch items-center rounded border border-line-input bg-surface px-3.5 text-sm font-semibold text-ink no-underline hover:bg-surface-subtle"
        >
          Open recording
        </a>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 rounded-card bg-surface-subtle px-4 py-4">
          <span className="text-sm text-ink-2">{reviewed ? "Score shown now" : "AI score"}</span>
          <span className={cx("text-hero font-semibold", SCORE_INK[scoreBand(shown)])}>{shown}</span>
          {reviewed && <span className="text-small text-muted">Set by a reviewer; the AI gave {item.ai_score}.</span>}
          {rationale && <p className="m-0 text-sm text-ink-2">{rationale}</p>}
        </div>
        <div className="flex flex-col gap-1.5 rounded-card border border-warning-border bg-warning-surface px-4 py-4">
          <span className="text-sm text-warning-ink">{firstName} proposes</span>
          <span className="text-hero font-semibold text-warning-ink">{item.proposed_score}</span>
          <p className="m-0 text-sm text-ink-2">“{item.comment}”</p>
          {spokenAt !== null && (
            <div>
              <TimeButton ms={spokenAt} player={player} label="the moment named" word="Play" />
            </div>
          )}
        </div>
      </div>

      {item.evidence.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="m-0 text-md font-semibold">Evidence the AI used</h3>
          <ol className="m-0 flex list-none flex-col gap-2 p-0">
            {item.evidence.map((e, i) => (
              <li
                key={i}
                className="flex items-start justify-between gap-3 rounded-card border border-line-subtle px-4 py-3"
              >
                <q className="pt-1.5 text-ink [quotes:none]">{e.quote}</q>
                <TimeButton ms={e.start_ms} player={player} label="quote" />
              </li>
            ))}
          </ol>
        </div>
      )}

      {item.raised_by_me ? (
        <p className="m-0 rounded-card border border-line-subtle bg-surface-subtle px-4 py-3 text-ink-2">
          You raised this dispute, so another reviewer, manager or administrator decides it.
        </p>
      ) : item.status !== "open" ? (
        <p className="m-0 text-sm text-muted">This dispute was {item.status}.</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <label htmlFor={noteId} className="text-sm font-semibold text-ink">
                Note to {firstName}
              </label>
              <span className="text-small text-muted">Shown with your decision. Required unless you accept.</span>
            </div>
            <textarea
              id={noteId}
              value={note}
              maxLength={500}
              rows={3}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Explain the decision in one or two sentences"
              aria-describedby={error ? errorId : undefined}
              className="rounded border border-line-input bg-surface px-3 py-2 text-ink placeholder:text-muted-2"
            />
          </div>
          {choosing && (
            <fieldset className="m-0 flex flex-wrap items-center gap-2 border-0 p-0">
              <legend className="mb-1.5 p-0 text-sm font-semibold">Final score</legend>
              {otherScores.map((s) => (
                <label
                  key={s}
                  className="flex min-h-touch min-w-touch cursor-pointer items-center justify-center rounded border border-line-input px-3 font-semibold has-[:checked]:border-primary has-[:checked]:bg-primary-tint has-[:checked]:text-primary"
                >
                  <input
                    type="radio"
                    name={`final-${item.id}`}
                    value={s}
                    checked={other === s}
                    onChange={() => setOther(s)}
                    className="sr-only"
                  />
                  {s}
                </label>
              ))}
              <Button
                disabled={other === null || sending}
                onClick={() => other !== null && void decide({ decision: "accepted", final_score: other })}
              >
                {other === null ? "Choose a score" : `Set score ${other}`}
              </Button>
            </fieldset>
          )}
          {error && (
            <p id={errorId} role="alert" className="m-0 text-sm text-danger">
              {error}
            </p>
          )}
          <div className="grid gap-2 sm:grid-cols-3">
            <Button
              disabled={sending}
              onClick={() => void decide({ decision: "accepted", final_score: item.proposed_score })}
            >
              Accept {item.proposed_score}
            </Button>
            <Button
              variant="secondary"
              disabled={sending || !hasNote}
              onClick={() => void decide({ decision: "rejected" })}
            >
              {reviewed ? "Keep score" : "Keep AI score"} {shown}
            </Button>
            <Button
              variant="secondary"
              aria-expanded={choosing}
              disabled={sending || !hasNote || otherScores.length === 0}
              onClick={() => setChoosing((c) => !c)}
            >
              Set a different score
            </Button>
          </div>
          <p className="m-0 text-small text-muted">
            Keeping the score or setting a different one needs a note. Your decision replaces the AI score in the
            report, keeps the AI score in history, and is added to the calibration set.
          </p>
        </div>
      )}
    </section>
  );
}
