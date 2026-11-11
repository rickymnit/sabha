// /reviews and /reviews/:id (UI v2, docs/design/v2/05-reviews.png; ADR 0007, P6.7) for owners, admins, managers and
// reviewers: decisions the AI should not make alone. One queue on the left (open disputes and recordings Sabha
// paused on, filtered by Disputes, Speakers and Other) and the selected decision on the right. The selection is in
// the address: /reviews/<recording id> for a paused recording (links from the bell and the report), or
// ?item=d:<dispute id> for a dispute; ?tab=disputes|speakers|other picks the filter.

import { useEffect, useRef, useState } from "react";
import { useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";

import { useAnalysis, useDisputes, useResolveDispute, useReviews, useTranscript } from "../api/hooks";
import type { Me } from "../api/types";
import { Button, EmptyState, Icon, PageHeader, Panel, Skeleton, SkeletonGroup, useToast } from "../design";
import type { Resolution } from "../features/disputes/types";
import { DisputeDecision } from "../features/reviews/DisputeDecision";
import { NeedsReviewDecision } from "../features/reviews/NeedsReviewDecision";
import { buildQueue, recordingKey, type DisputeEntry } from "../features/reviews/queue";
import { QueueList, type QueueFilter } from "../features/reviews/QueueList";
import { useSamplePlayer } from "../features/reviews/useSamplePlayer";

const FILTERS: readonly QueueFilter[] = ["disputes", "speakers", "other"];

function DisputePane({ item, onDecided }: { item: DisputeEntry; onDecided: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const resolve = useResolveDispute();
  const analysis = useAnalysis(item.recording_id);
  // Audio only when someone presses play: the transcript call returns a fresh presigned playback URL.
  const transcript = useTranscript(item.recording_id, false);
  const player = useSamplePlayer(transcript.data?.playback_url ?? undefined, async () => {
    const fresh = await transcript.refetch();
    return fresh.data?.playback_url ?? undefined;
  });
  const payload = analysis.data;
  const dimension =
    payload && "dimensions" in payload ? payload.dimensions.find((d) => d.key === item.dimension_key) : undefined;
  const rationale = dimension && "rationale" in dimension ? dimension.rationale : null;
  const href = `/recordings/${encodeURIComponent(item.recording_id)}`;

  const onResolve = async (resolution: Resolution) => {
    await resolve.mutateAsync({ id: item.id, resolution });
    const first = (item.raised_by_name ?? item.person_name ?? "").split(" ")[0];
    toast.show({
      tone: "success",
      title: resolution.decision === "accepted" ? `Score set to ${resolution.final_score}` : "Score kept",
      message: first ? `${first} is told about your decision.` : undefined,
      duration: 6000,
    });
    onDecided();
  };

  return (
    <DisputeDecision
      key={item.id}
      item={item}
      rationale={rationale}
      player={player}
      recordingHref={href}
      onOpenRecording={() => navigate(href)}
      onResolve={onResolve}
    />
  );
}

export function ReviewQueuePage() {
  const me = useOutletContext<Me>();
  const navigate = useNavigate();
  const { id: routeId } = useParams();
  const [params, setParams] = useSearchParams();
  const reviews = useReviews();
  const disputes = useDisputes();
  const [decided, setDecided] = useState(0);
  const detailRef = useRef<HTMLDivElement>(null);
  const scrollPending = useRef(false);

  const tab = params.get("tab");
  const filter: QueueFilter = FILTERS.includes(tab as QueueFilter) ? (tab as QueueFilter) : "all";
  const items = buildQueue(disputes.data?.items ?? [], reviews.data?.items ?? [], me.tenant.labels);
  const shown = filter === "all" ? items : items.filter((i) => i.group === filter);
  const wanted = routeId ? recordingKey(routeId) : (params.get("item") ?? undefined);
  const selected = items.find((i) => i.key === wanted) ?? (routeId ? undefined : shown[0]);

  const selectedKey = selected?.key;
  useEffect(() => {
    if (!scrollPending.current) return;
    scrollPending.current = false;
    // On a phone the decision sits under the list: bring it into view.
    if (window.matchMedia?.("(max-width: 1023px)").matches) detailRef.current?.scrollIntoView({ block: "start" });
  }, [selectedKey]);

  const select = (key: string) => {
    const next = new URLSearchParams(params);
    next.set("item", key);
    navigate({ pathname: "/reviews", search: `?${next.toString()}` }, { replace: Boolean(routeId) });
    scrollPending.current = true;
  };
  const setFilter = (value: QueueFilter) => {
    const next = new URLSearchParams();
    if (value !== "all") next.set("tab", value);
    if (routeId) navigate({ pathname: "/reviews", search: next.size ? `?${next.toString()}` : "" });
    else setParams(next, { replace: true });
  };
  const decidedOne = () => {
    setDecided((n) => n + 1);
    const next = new URLSearchParams(params);
    next.delete("item");
    navigate({ pathname: "/reviews", search: next.size ? `?${next.toString()}` : "" }, { replace: true });
  };

  const failed = reviews.isError || disputes.isError;
  const loading = reviews.isPending || disputes.isPending;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reviews"
        description="Decisions the AI should not make alone. Disputed scores and unclear speakers wait here for a person."
      />
      {failed ? (
        <Panel>
          <EmptyState
            icon={<Icon name="alert" size={26} />}
            title="We couldn't load the reviews"
            description="Please try again in a moment."
            action={
              <Button
                onClick={() => {
                  void reviews.refetch();
                  void disputes.refetch();
                }}
              >
                Try again
              </Button>
            }
          />
        </Panel>
      ) : loading ? (
        <Panel>
          <SkeletonGroup label="Loading reviews" className="flex flex-col gap-3">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-4 w-1/3" />
          </SkeletonGroup>
        </Panel>
      ) : items.length === 0 && !routeId ? (
        <Panel>
          <EmptyState
            className="py-14"
            icon={<Icon name="reviews" size={26} />}
            title={decided > 0 ? "All decided" : "Nothing waiting for a decision"}
            description={
              decided > 0
                ? `You made ${decided} ${decided === 1 ? "decision" : "decisions"}. New disputes and unclear speakers will appear here.`
                : `When someone disputes a score, or Sabha is unsure who the ${me.tenant.labels.person.toLowerCase()} is, it appears here.`
            }
          />
        </Panel>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
          <QueueList
            items={items}
            filter={filter}
            onFilter={setFilter}
            selectedKey={selected?.key ?? wanted}
            onSelect={select}
            decided={decided}
          />
          <div ref={detailRef} className="min-w-0 scroll-mt-4">
            {selected?.dispute ? (
              <DisputePane item={selected.dispute} onDecided={decidedOne} />
            ) : selected?.recording || routeId ? (
              <NeedsReviewDecision
                key={selected?.recording?.id ?? routeId}
                recordingId={selected?.recording?.id ?? routeId ?? ""}
                me={me}
                onDone={decidedOne}
                onOpenRecording={() =>
                  navigate(`/recordings/${encodeURIComponent(selected?.recording?.id ?? routeId ?? "")}`)
                }
              />
            ) : (
              <Panel>
                <EmptyState
                  className="py-10"
                  icon={<Icon name="reviews" size={26} />}
                  title="Nothing waiting here"
                  description="Choose another filter to see the rest."
                />
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
