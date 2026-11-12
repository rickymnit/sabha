// What the person analysed sees at the top of a report a manager once shared with a note (UI v2 sharing; the
// "Share with" step itself was removed when coaching became private, 2026-11-12).

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
