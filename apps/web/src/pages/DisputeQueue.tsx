// The Disputes tab of /reviews (P6.7): scores someone asked a reviewer to look at again. The list is on the left
// and the selected dispute, with its quotes and the decision form, on the right. Accepting sets the reviewer's score
// (the AI score stays as history); every decision needs a note, which the person reads.

import { useId, useState } from "react";

import { useResolveDispute } from "../api/hooks";
import { Card, EmptyState, Icon, Panel } from "../design";
import type { DisputePage, Resolution } from "../features/disputes/types";
import { ReviewDetail } from "../features/reviews/ReviewsPage";

export interface DisputeQueueProps {
  page: DisputePage;
  personWord: string;
}

export function DisputeQueue({ page, personWord }: DisputeQueueProps) {
  const resolve = useResolveDispute();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const listId = useId();
  const items = page.items;
  const selected = items.find((i) => i.id === selectedId) ?? items[0];

  if (items.length === 0) {
    return (
      <Panel>
        <EmptyState
          className="py-14"
          icon={<Icon name="reviews" size={26} />}
          title="No disputed scores"
          description={`When a ${personWord.toLowerCase()} or their manager disputes a score, it appears here for you to decide.`}
        />
      </Panel>
    );
  }
  const onResolve = async (id: string, resolution: Resolution) => {
    await resolve.mutateAsync({ id, resolution });
    setSelectedId(null);
  };
  return (
    <div className="flex flex-wrap items-start gap-5">
      <Card className="flex min-w-0 flex-[1_1_320px] flex-col gap-1.5 p-3">
        <h2 id={listId} className="mx-1 my-1 text-lg font-semibold">
          Disputed scores ({items.length})
        </h2>
        <ul aria-labelledby={listId} className="m-0 flex list-none flex-col gap-1.5 p-0">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={item.id === selected?.id}
                onClick={() => setSelectedId(item.id)}
                className="flex min-h-touch w-full flex-col items-start gap-0.5 rounded-seg-outer border border-line-subtle px-3 py-2 text-left aria-pressed:border-primary aria-pressed:bg-primary-tint-subtle"
              >
                <span className="font-semibold">{item.recording_title}</span>
                <span className="text-small text-muted">
                  {item.dimension_name}: {item.current_score ?? item.ai_score} → {item.proposed_score}
                  {" · "}
                  {[item.person_name, item.unit].filter(Boolean).join(", ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      {selected && (
        <ReviewDetail
          key={selected.id}
          item={selected}
          onResolve={onResolve}
          recordingHref={(rid) => `/recordings/${encodeURIComponent(rid)}`}
        />
      )}
    </div>
  );
}
