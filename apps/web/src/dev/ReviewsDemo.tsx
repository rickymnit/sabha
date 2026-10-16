// Demo of the reviewer queue (P6.7), served at /dev/reviews in development only (see main.tsx). Mock data; the
// real page reads GET /v1/reviews and posts to /v1/disputes/{id}/resolve.

import { useState } from "react";

import type { Resolution, ReviewItem } from "../features/disputes/types";
import { ReviewsPage } from "../features/reviews/ReviewsPage";
import { mockReviewItems } from "../features/reviews/mock";

export default function ReviewsDemo() {
  const [items, setItems] = useState<ReviewItem[]>(() => mockReviewItems());
  async function resolve(id: string, resolution: Resolution) {
    setItems((all) =>
      all.map((item) => (item.id === id && item.kind === "dispute" ? { ...item, status: resolution.decision } : item)),
    );
  }
  return (
    <main className="mx-auto max-w-[1200px] p-6">
      <ReviewsPage items={items} onResolve={resolve} recordingHref={(id) => `/dev/report?recording=${id}`} />
    </main>
  );
}
