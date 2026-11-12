// "For your next call": the coaching for the next conversation (founder's Sales Executive dashboard doc,
// 2026-11-12): one question to ask, one thing to explain better and one practice point, each at the moment it rests
// on. Private to the person analysed; the API sends it to no one else.

import { useId } from "react";

import { TimeChip } from "./SalesPanels";
import type { NextTime, Tip } from "./types";

const ROWS = [
  { key: "practice_point", label: "Practise in your next call" },
  { key: "question_to_ask", label: "A question you could ask" },
  { key: "explain_better", label: "Explain better next time" },
] as const;

export function NextTimePanel({ coaching, onSeek }: { coaching: NextTime; onSeek: (ms: number) => void }) {
  const headingId = useId();
  const rows = ROWS.map((r) => ({ ...r, tip: coaching[r.key] })).filter(
    (r): r is typeof r & { tip: Tip } => r.tip !== null,
  );
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby={headingId} className="min-w-0 rounded-panel border border-line bg-surface">
      <div className="flex flex-col gap-0.5 border-b border-line-subtle px-5 py-3.5">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          For your next call
        </h2>
        <span className="text-small text-muted">Private to you. Each tip points at the moment it comes from.</span>
      </div>
      <ul className="m-0 flex list-none flex-col p-0">
        {rows.map(({ key, label, tip }) => (
          <li key={key} className="flex items-start gap-3 border-b border-line-subtle px-5 py-3.5 last:border-b-0">
            <TimeChip ms={tip.evidence.start_ms} onSeek={onSeek} />
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="text-small font-semibold text-muted">{label}</span>
              <span className="text-ink">{tip.text}</span>
              {tip.product_info && (
                <details className="mt-1 rounded-card bg-surface-faint px-3 py-2">
                  <summary className="cursor-pointer text-small font-semibold text-primary-hover">
                    Review: {tip.product_info.title}
                  </summary>
                  <p className="m-0 mt-1.5 whitespace-pre-line text-small text-ink-2">{tip.product_info.body}</p>
                </details>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
