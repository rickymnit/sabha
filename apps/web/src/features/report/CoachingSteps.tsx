// The coaching steps above a report (UI v2, docs/design/v2/03-lesson-report.png), for managers: the report is
// ready, share it with the person (they see strengths first), then talk it through in the next one-to-one. Sharing
// marks step 2 done (shared_at); step 3 is guidance, not tracked.

import { cx } from "../../design";
import { formatIst } from "./format";

export interface CoachingStepsProps {
  /** When the report was made (ISO). */
  readyAt: string;
  /** When it was last shared with the person (ISO), if it was. */
  sharedAt: string | null | undefined;
  firstName: string;
}

function Step({
  n,
  state,
  title,
  note,
}: {
  n: number;
  state: "done" | "current" | "todo";
  title: string;
  note: string;
}) {
  return (
    <li className="flex min-w-0 items-center gap-2.5">
      <span
        aria-hidden="true"
        className={cx(
          "flex size-7 shrink-0 items-center justify-center rounded-full text-small font-bold",
          state === "done" && "bg-success text-surface",
          state === "current" && "bg-primary text-surface",
          state === "todo" && "border border-line-input text-muted",
        )}
      >
        {state === "done" ? "✓" : n}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="text-sm font-semibold text-ink">
          {title}
          <span className="sr-only">{state === "done" ? ", done" : state === "current" ? ", next" : ""}</span>
        </span>
        <span className="text-caption text-muted">{note}</span>
      </span>
    </li>
  );
}

export function CoachingSteps({ readyAt, sharedAt, firstName }: CoachingStepsProps) {
  return (
    <section
      aria-label="Coaching"
      className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-panel border border-line bg-surface px-5 py-3"
    >
      <span className="text-sm font-semibold text-ink">Coaching</span>
      <ol className="m-0 flex flex-wrap items-center gap-x-6 gap-y-3 p-0 [&>li]:list-none">
        <Step n={1} state="done" title="Report ready" note={formatIst(readyAt).split(",")[0] ?? ""} />
        <li aria-hidden="true" className="hidden h-px w-10 bg-line sm:block" />
        <Step
          n={2}
          state={sharedAt ? "done" : "current"}
          title={`Share with ${firstName}`}
          note={sharedAt ? `Shared ${formatIst(sharedAt).split(",")[0] ?? ""}` : "They see strengths first"}
        />
        <li aria-hidden="true" className="hidden h-px w-10 bg-line sm:block" />
        <Step n={3} state={sharedAt ? "current" : "todo"} title="Talk it through" note="In your next 1:1" />
      </ol>
    </section>
  );
}

/** What the person analysed sees at the top when their manager shared the report with a note. */
export function SharedNote({ from, note }: { from: string; note: string }) {
  return (
    <section
      aria-label={`Note from ${from}`}
      className="flex items-start gap-3 rounded-panel border border-line bg-surface px-5 py-4"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-ink text-small font-semibold text-surface">
        {from
          .split(" ")
          .map((w) => w[0])
          .join("")
          .slice(0, 2)
          .toUpperCase()}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-small text-muted">
          <span className="font-semibold text-ink">{from}</span> shared this with a note
        </span>
        <span className="text-ink">{note}</span>
      </span>
    </section>
  );
}
