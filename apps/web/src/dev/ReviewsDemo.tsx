// Demo of the Reviews page (UI v2, docs/design/v2/05-reviews.png), served at /dev/reviews in development only (see
// main.tsx). Mock data and no API: the queue and the dispute decision. The real page (pages/ReviewQueuePage.tsx)
// reads GET /v1/disputes and GET /v1/reviews, and shows the "who is the speaker?" decision from the API.

import { useState } from "react";

import type { RecordingItem } from "../api/types";
import { DisputeDecision } from "../features/reviews/DisputeDecision";
import { mockReviewItems } from "../features/reviews/mock";
import { buildQueue, type DisputeEntry } from "../features/reviews/queue";
import { QueueList, type QueueFilter } from "../features/reviews/QueueList";

const LABELS = { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                 unit: "Class", manager: "Coordinator" }; // prettier-ignore

function paused(): RecordingItem[] {
  return mockReviewItems().flatMap((i) =>
    i.kind === "needs_review"
      ? [{ id: i.recording_id, title: i.recording_title, type: "teaching", status: "NEEDS_REVIEW", status_reason: i.reason,
           status_note: "We could not tell the speakers apart reliably.", person: null, unit_id: null, file_name: null,
           duration_ms: null, created_at: i.created_at, status_changed_at: i.created_at, completed_at: null,
           overall_score: null, audio_deleted_at: null } satisfies RecordingItem] // prettier-ignore
      : [],
  );
}

export default function ReviewsDemo() {
  const [disputes, setDisputes] = useState<DisputeEntry[]>(() =>
    mockReviewItems().filter((i): i is DisputeEntry => i.kind === "dispute"),
  );
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [selected, setSelected] = useState<string>();
  const [decided, setDecided] = useState(0);
  const items = buildQueue(disputes, paused(), LABELS);
  const current = items.find((i) => i.key === selected) ?? items[0];
  const player = { play: async () => {}, playing: null };

  return (
    <main className="mx-auto flex max-w-[1240px] flex-col gap-6 p-6">
      <h1 className="m-0 text-title font-semibold">Reviews</h1>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
        <QueueList
          items={items}
          filter={filter}
          onFilter={setFilter}
          selectedKey={current?.key}
          onSelect={setSelected}
          decided={decided}
        />
        {current?.dispute ? (
          <DisputeDecision
            key={current.key}
            item={current.dispute}
            rationale="Two checks in 52 minutes; the class moved on without evidence most students followed."
            player={player}
            recordingHref="/dev/report"
            onResolve={async () => {
              setDisputes((all) => all.filter((d) => d.id !== current.dispute?.id));
              setDecided((n) => n + 1);
            }}
          />
        ) : (
          <p className="text-muted">The speaker question needs the API; open /reviews in the app.</p>
        )}
      </div>
    </main>
  );
}
