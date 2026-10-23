// /reviews/:id (ADR 0007): one recording waiting for review. For unclear roles the reviewer listens to a few lines
// from each voice and picks the staff member; Sabha then rebuilds the transcript with those roles and scores it.
// Any recording can instead be closed as not usable, with a note. Both are audited by the API.

import { useEffect, useRef, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { useRecording, useResolveReview, useSpeakers, useTranscript } from "../api/hooks";
import type { Me, ReviewSpeaker } from "../api/types";
import { capitalise, formatWhen } from "../app/format";
import { Button, EmptyState, Icon, PageHeader, Panel, Skeleton, SkeletonGroup, cx, useToast } from "../design";
import { SmallPlayIcon } from "../features/report/icons";
import { formatClock } from "../features/transcript/text";

const UNCLEAR_ROLES = "unclear_roles";

/** Plays one stretch of the recording at a time, from a presigned URL (fetching a fresh one when it has expired). */
function useSamplePlayer(url: string | undefined, refresh: () => Promise<string | undefined>) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const stopAt = useRef<number | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);

  useEffect(() => {
    const element = new Audio();
    element.preload = "none";
    const onTime = () => {
      if (stopAt.current !== null && element.currentTime * 1000 >= stopAt.current) {
        element.pause();
        stopAt.current = null;
        setPlaying(null);
      }
    };
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("pause", () => setPlaying(null));
    audio.current = element;
    return () => {
      element.pause();
      element.removeEventListener("timeupdate", onTime);
      audio.current = null;
    };
  }, []);

  const play = async (startMs: number, endMs: number) => {
    const element = audio.current;
    if (!element) return;
    if (playing === startMs) {
      element.pause();
      return;
    }
    const source = url ?? (await refresh());
    if (!source) return;
    if (element.src !== source) element.src = source;
    element.currentTime = startMs / 1000;
    stopAt.current = endMs;
    setPlaying(startMs);
    try {
      await element.play();
    } catch {
      // The URL expired: fetch a fresh one and try once more.
      const fresh = await refresh();
      if (!fresh) return setPlaying(null);
      element.src = fresh;
      element.currentTime = startMs / 1000;
      await element.play().catch(() => setPlaying(null));
    }
  };
  return { play, playing };
}

function SpeakerCard({
  speaker,
  index,
  chosen,
  onChoose,
  guessLabel,
  playing,
  onPlay,
}: {
  speaker: ReviewSpeaker;
  index: number;
  chosen: boolean;
  onChoose: () => void;
  guessLabel: string | null;
  playing: number | null;
  onPlay: (startMs: number, endMs: number) => void;
}) {
  // prettier-ignore
  return (
    <li
      className={cx(
        "flex flex-col gap-3 rounded-card border p-4",
        chosen ? "border-primary-border bg-primary-tint-subtle" : "border-line-subtle bg-surface",
      )}
    >
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="radio"
          name="staff-speaker"
          checked={chosen}
          onChange={onChoose}
          className="m-0 mt-1 h-4.5 w-4.5 shrink-0 accent-primary"
        />
        <span className="flex flex-col gap-0.5">
          <span className="font-semibold text-ink">Voice {index + 1}</span>
          <span className="text-small text-muted">
            {Math.round(speaker.share * 100)}% of the speaking time
            {guessLabel ? `. Sabha guessed: ${guessLabel}` : ""}
          </span>
        </span>
      </label>
      <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={`Lines from voice ${index + 1}`}>
        {speaker.samples.map((sample) => (
          <li key={sample.start_ms} className="flex items-start gap-3 rounded border border-track bg-surface px-3 py-2">
            <Button
              variant="secondary"
              aria-label={`${playing === sample.start_ms ? "Stop" : "Play"} voice ${index + 1} at ${formatClock(sample.start_ms)}`}
              onClick={() => onPlay(sample.start_ms, sample.end_ms)}
              className="min-h-[36px] shrink-0 gap-1.5 px-2.5 text-small"
            >
              {playing === sample.start_ms ? <Icon name="close" size={12} /> : <SmallPlayIcon />}
              {formatClock(sample.start_ms)}
            </Button>
            <span className="pt-1.5 text-sm text-ink-2">{sample.text}</span>
          </li>
        ))}
      </ul>
    </li>
  );
}

export function ReviewPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const recording = useRecording(id);
  const rolesQuestion = recording.data?.status === "NEEDS_REVIEW" && recording.data.status_reason === UNCLEAR_ROLES;
  const speakers = useSpeakers(id, rolesQuestion);
  const transcript = useTranscript(id, rolesQuestion);
  const resolve = useResolveReview(id);
  const [staff, setStaff] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const player = useSamplePlayer(transcript.data?.playback_url, async () => {
    const fresh = await transcript.refetch();
    return fresh.data?.playback_url;
  });

  const person = labels.person.toLowerCase();
  const thing = labels.recording.toLowerCase();
  const roleLabel = (role: string | null) =>
    role === null ? null : role === speakers.data?.choices[0] ? capitalise(labels.person) : capitalise(role);

  const decide = async (decision: Parameters<typeof resolve.mutateAsync>[0], done: string) => {
    try {
      await resolve.mutateAsync(decision);
      toast.show({ tone: "success", title: done, duration: 6000 });
      navigate("/reviews");
    } catch (error) {
      toast.show({
        tone: "error",
        title: "That did not go through",
        message: error instanceof ApiError ? error.message : "Please try again.",
        requestId: error instanceof ApiError ? error.requestId : undefined,
      });
    }
  };

  if (recording.isError) {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name="search" size={26} />}
          title={`We couldn't find this ${thing}`}
          action={<Button onClick={() => navigate("/reviews")}>Back to reviews</Button>}
        />
      </Panel>
    );
  }
  if (!recording.data) {
    return (
      <SkeletonGroup label="Loading the review" className="flex flex-col gap-3">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-40 w-full" />
      </SkeletonGroup>
    );
  }
  const r = recording.data;
  if (r.status !== "NEEDS_REVIEW") {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name="reviews" size={26} />}
          title="This review is done"
          description={`The ${thing} is no longer waiting for review.`}
          action={
            <>
              <Button onClick={() => navigate(`/recordings/${r.id}`)}>Open the {thing}</Button>
              <Button variant="secondary" onClick={() => navigate("/reviews")}>
                Back to reviews
              </Button>
            </>
          }
        />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumbs={[{ label: "Reviews", href: "/reviews" }, { label: r.title }]}
        title={r.title}
        description={[r.person?.name, r.unit_name, `uploaded ${formatWhen(r.created_at).toLowerCase()}`]
          .filter(Boolean)
          .join(", ")}
      />
      <div className="flex items-start gap-3 rounded-card border border-warning-border bg-warning-surface px-4 py-3.5">
        <Icon name="alert" className="mt-0.5 shrink-0 text-warning-ink" />
        <div className="flex flex-col gap-0.5">
          <p className="m-0 font-semibold text-warning-ink">Why Sabha paused</p>
          <p className="m-0 text-ink-2">{r.status_note}</p>
        </div>
      </div>

      {rolesQuestion && (
        <Panel
          title={`Who is the ${person}?`}
          description={`Listen to a few lines from each voice and choose the ${person}. Sabha then scores the ${thing} as usual. Only the ${person} is scored.`}
        >
          {speakers.isPending ? (
            <Skeleton className="h-48 w-full" />
          ) : speakers.isError ? (
            <p className="m-0 text-danger">The voices could not be loaded. Please try again in a moment.</p>
          ) : (
            <>
              <ul className="m-0 grid list-none gap-3 p-0 lg:grid-cols-2" aria-label="Voices">
                {speakers.data.speakers.map((speaker, index) => (
                  <SpeakerCard
                    key={speaker.label}
                    speaker={speaker}
                    index={index}
                    chosen={staff === speaker.label}
                    onChoose={() => setStaff(speaker.label)}
                    guessLabel={roleLabel(speaker.guess)}
                    playing={player.playing}
                    onPlay={(start, end) => void player.play(start, end)}
                  />
                ))}
              </ul>
              <div className="flex flex-wrap items-center gap-3 border-t border-line-subtle pt-4">
                <Button
                  disabled={staff === null || resolve.isPending}
                  onClick={() =>
                    void decide(
                      { action: "confirm_roles", staff_speaker: staff ?? "" },
                      `Thanks. Sabha is scoring the ${thing} now.`,
                    )
                  }
                >
                  {resolve.isPending ? "Saving…" : `Confirm and score`}
                </Button>
                <span className="text-small text-muted">
                  {staff === null
                    ? `Choose the voice of the ${person} first.`
                    : `Every other voice is treated as ${roleLabel(speakers.data.choices[1] ?? null)?.toLowerCase() ?? "the others"}.`}
                </span>
              </div>
            </>
          )}
        </Panel>
      )}

      <Panel
        title="Not usable?"
        description={`If this ${thing} cannot be scored, close it. It is marked failed with your note, and nothing is scored.`}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="close-note" className="text-sm font-semibold text-ink">
            Why is it not usable?
          </label>
          <textarea
            id="close-note"
            value={note}
            maxLength={500}
            rows={3}
            onChange={(e) => setNote(e.target.value)}
            placeholder="For example: the recorder was in a bag; nothing can be heard."
            className="rounded border border-line-input bg-surface px-3 py-2 text-ink placeholder:text-muted-2"
          />
        </div>
        <div>
          <Button
            variant="secondary"
            disabled={note.trim() === "" || resolve.isPending}
            onClick={() =>
              void decide({ action: "close", note: note.trim() }, `The ${thing} was closed as not usable.`)
            }
          >
            Close as not usable
          </Button>
        </div>
      </Panel>
    </div>
  );
}
