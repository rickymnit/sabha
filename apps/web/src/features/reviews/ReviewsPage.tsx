// Reviewer queue (P6.7): open disputes and recordings that need review, with a detail view to resolve a dispute.
// Accepting sets a human score (the AI score stays in history); every resolution needs a note.

import { useId, useMemo, useState, type FormEvent } from "react";

import { Button, Card, PageHeader, SegmentedControl } from "../../design";
import { formatClock } from "../transcript";
import type { Resolution, ReviewItem } from "../disputes/types";

type KindFilter = "all" | "dispute" | "needs_review";
type StatusFilter = "open" | "all";

export interface ReviewsPageProps {
  items: readonly ReviewItem[];
  onResolve: (id: string, resolution: Resolution) => Promise<void>;
  /** Builds the link to a recording's report. */
  recordingHref: (recordingId: string) => string;
}

const isOpen = (item: ReviewItem) => item.status === "open";

export function ReviewsPage({ items, onResolve, recordingHref }: ReviewsPageProps) {
  const [kind, setKind] = useState<KindFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("open");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const shown = useMemo(
    () => items.filter((i) => (kind === "all" || i.kind === kind) && (status === "all" || isOpen(i))),
    [items, kind, status],
  );
  const selected = shown.find((i) => i.id === selectedId) ?? shown[0];
  const listId = useId();

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <PageHeader title="Reviews" description="Disputed scores and recordings that need a person to look at them." />
      <div className="flex flex-wrap gap-3">
        <SegmentedControl
          label="Show"
          value={kind}
          onChange={(v) => setKind(v as KindFilter)}
          options={[
            { value: "all", label: "All" },
            { value: "dispute", label: "Disputes" },
            { value: "needs_review", label: "Needs review" },
          ]}
        />
        <SegmentedControl
          label="Status"
          value={status}
          onChange={(v) => setStatus(v as StatusFilter)}
          options={[
            { value: "open", label: "Open" },
            { value: "all", label: "All" },
          ]}
        />
      </div>
      <div className="flex flex-wrap items-start gap-5">
        <Card className="flex min-w-0 flex-[1_1_320px] flex-col gap-1.5 p-3">
          <h2 id={listId} className="mx-1 my-1 text-lg font-semibold">
            Queue ({shown.length})
          </h2>
          {shown.length === 0 ? (
            <p className="m-1 text-sm text-muted">Nothing to review.</p>
          ) : (
            <ul aria-labelledby={listId} className="m-0 flex list-none flex-col gap-1.5 p-0">
              {shown.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-pressed={item.id === selected?.id}
                    onClick={() => setSelectedId(item.id)}
                    className="flex min-h-touch w-full flex-col items-start gap-0.5 rounded-seg-outer border border-line-subtle px-3 py-2 text-left aria-pressed:border-primary aria-pressed:bg-primary-tint-subtle"
                  >
                    <span className="font-semibold">{item.recording_title}</span>
                    <span className="text-small text-muted">
                      {item.kind === "dispute"
                        ? `Dispute: ${item.dimension_name}, ${item.ai_score} → ${item.proposed_score}`
                        : `Needs review: ${item.reason}`}
                      {" · "}
                      {item.person_name}, {item.unit}
                      {isOpen(item) ? "" : ` · ${item.status}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {selected && (
          <ReviewDetail key={selected.id} item={selected} onResolve={onResolve} recordingHref={recordingHref} />
        )}
      </div>
    </div>
  );
}

function ReviewDetail({
  item,
  onResolve,
  recordingHref,
}: {
  item: ReviewItem;
  onResolve: ReviewsPageProps["onResolve"];
  recordingHref: ReviewsPageProps["recordingHref"];
}) {
  const headingId = useId();
  const errorId = useId();
  const [finalScore, setFinalScore] = useState<number | null>(item.kind === "dispute" ? item.proposed_score : null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function resolve(decision: Resolution["decision"], event?: FormEvent) {
    event?.preventDefault();
    if (!note.trim()) return setError("Add a note: the person will read it.");
    if (decision === "accepted" && finalScore === null) return setError("Choose the final score.");
    setError(null);
    setSending(true);
    try {
      await onResolve(item.id, {
        decision,
        note: note.trim(),
        ...(decision === "accepted" && finalScore !== null ? { final_score: finalScore } : {}),
      });
    } catch {
      setError("The decision could not be saved. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-[999_1_480px] flex-col gap-4 rounded-panel border border-line bg-surface px-6 py-5"
    >
      <h2 id={headingId} className="m-0 text-xl font-semibold">
        {item.recording_title}
      </h2>
      <p className="m-0 text-sm text-muted">
        {item.person_name}, {item.unit} · <a href={recordingHref(item.recording_id)}>Open the recording</a>
      </p>
      {item.kind === "needs_review" ? (
        <p className="m-0">
          This recording needs a person to look at it: <span className="font-semibold">{item.reason}</span>.
        </p>
      ) : (
        <>
          <dl className="m-0 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-muted">Dimension</dt>
            <dd className="m-0 font-semibold">{item.dimension_name}</dd>
            <dt className="text-muted">AI score</dt>
            <dd className="m-0">{item.ai_score}</dd>
            <dt className="text-muted">Proposed score</dt>
            <dd className="m-0">{item.proposed_score}</dd>
            <dt className="text-muted">Reason given</dt>
            <dd className="m-0">{item.comment}</dd>
          </dl>
          <div className="flex flex-col gap-2">
            <h3 className="m-0 text-table font-semibold">Evidence the AI used</h3>
            <ol className="m-0 flex list-none flex-col gap-2 p-0">
              {item.evidence.map((e, i) => (
                <li key={i} className="rounded-card border border-track bg-surface-subtle px-3.5 py-2.5">
                  <q className="[quotes:none]">{e.quote}</q>{" "}
                  <span className="text-small text-muted">{formatClock(e.start_ms)}</span>
                </li>
              ))}
            </ol>
          </div>
          {item.status === "open" ? (
            <form onSubmit={(e) => void resolve("accepted", e)} noValidate className="flex flex-col gap-3">
              <fieldset className="m-0 border-0 p-0">
                <legend className="mb-1.5 p-0 text-sm font-semibold">Final score if accepted</legend>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <label
                      key={s}
                      className="flex min-h-touch min-w-touch cursor-pointer items-center justify-center gap-1.5 rounded border border-line-input px-3 has-[:checked]:border-primary has-[:checked]:bg-primary-tint"
                    >
                      <input
                        type="radio"
                        name="final"
                        value={s}
                        checked={finalScore === s}
                        onChange={() => setFinalScore(s)}
                      />
                      {s}
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="flex flex-col gap-1.5 text-sm font-semibold">
                Note to the person
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                  aria-describedby={error ? errorId : undefined}
                  className="rounded border border-line-input bg-surface p-3 font-normal"
                />
              </label>
              {error && (
                <p id={errorId} role="alert" className="m-0 text-sm text-danger">
                  {error}
                </p>
              )}
              <div className="flex gap-2">
                <Button type="submit" disabled={sending}>
                  Accept and set score
                </Button>
                <Button variant="secondary" type="button" disabled={sending} onClick={() => void resolve("rejected")}>
                  Reject
                </Button>
              </div>
            </form>
          ) : (
            <p className="m-0 text-sm text-muted">This dispute was {item.status}.</p>
          )}
        </>
      )}
    </section>
  );
}
