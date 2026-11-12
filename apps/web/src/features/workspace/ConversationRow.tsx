// One call or meeting in a list (Overview, My interactions): the client's name, then "Call · 10 Nov · 3 min", the
// client's interest and the score in words. A file name never shows: it means nothing to the reader.

import type { RecordingItem } from "../../api/types";
import { formatDuration, formatWhen } from "../../app/format";
import { InterestPill, KindLabel, ScoreVerdict } from "./parts";
import { clientOf, conversationName, pendingWords } from "./words";

export function ConversationRow({
  row,
  labels,
  onOpen,
}: {
  row: RecordingItem;
  labels?: Record<string, string>;
  onOpen: () => void;
}) {
  const done = row.status === "COMPLETED";
  const at = row.recorded_at ?? row.created_at;
  const client = clientOf(row);
  return (
    <li className="border-b border-line-subtle last:border-b-0">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1.5 bg-transparent px-5 py-3 text-left hover:bg-surface-faint"
      >
        <span className="flex min-w-0 flex-[1_1_220px] flex-col gap-0.5">
          <span className="truncate font-semibold text-ink">{conversationName(client, row.interaction, at)}</span>
          <span className="flex flex-wrap items-center gap-x-1.5 text-small text-muted">
            {/* without a client the name already says "Call on 5 Nov" */}
            {client ? (
              <>
                <KindLabel kind={row.interaction} />
                <span>· {formatWhen(at)}</span>
              </>
            ) : null}
            {row.duration_ms ? (
              <span>
                {client ? "· " : ""}
                {formatDuration(row.duration_ms)}
              </span>
            ) : null}
          </span>
        </span>
        {done ? (
          <span className="flex flex-wrap items-center gap-3">
            <InterestPill value={row.interest_level} labels={labels} />
            <ScoreVerdict score={row.overall_score} />
          </span>
        ) : (
          <span className="text-small text-muted">{pendingWords(row.status)}</span>
        )}
      </button>
    </li>
  );
}
