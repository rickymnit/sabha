// Right column of the Reviews page for a recording Sabha paused on (ADR 0007). For unclear roles the reviewer
// listens to a few lines from each voice and picks the staff member; Sabha then rebuilds the transcript with those
// roles and scores it. Any recording can instead be closed as not usable, with a note. Both are audited by the API.

import { useId, useState } from "react";

import { ApiError } from "../../api/client";
import { useRecording, useResolveReview, useSpeakers, useTranscript } from "../../api/hooks";
import type { Me, ReviewSpeaker } from "../../api/types";
import { capitalise, formatWhen } from "../../app/format";
import { Button, EmptyState, Icon, Skeleton, SkeletonGroup, cx, useToast } from "../../design";
import { SmallPlayIcon } from "../report/icons";
import { formatClock } from "../transcript/text";
import { useSamplePlayer, type SamplePlayer } from "./useSamplePlayer";

const UNCLEAR_ROLES = "unclear_roles";

function SpeakerCard({
  speaker,
  index,
  chosen,
  onChoose,
  guessLabel,
  player,
}: {
  speaker: ReviewSpeaker;
  index: number;
  chosen: boolean;
  onChoose: () => void;
  guessLabel: string | null;
  player: SamplePlayer;
}) {
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
              aria-label={`${player.playing === sample.start_ms ? "Stop" : "Play"} voice ${index + 1} at ${formatClock(sample.start_ms)}`}
              onClick={() => void player.play(sample.start_ms, sample.end_ms)}
              className="min-h-[36px] shrink-0 gap-1.5 px-2.5 text-small"
            >
              {player.playing === sample.start_ms ? <Icon name="close" size={12} /> : <SmallPlayIcon />}
              {formatClock(sample.start_ms)}
            </Button>
            <span className="pt-1.5 text-sm text-ink-2">{sample.text}</span>
          </li>
        ))}
      </ul>
    </li>
  );
}

export interface NeedsReviewDecisionProps {
  recordingId: string;
  me: Me;
  /** Called after a decision went through (the item leaves the queue). */
  onDone: () => void;
  onOpenRecording: () => void;
}

export function NeedsReviewDecision({ recordingId, me, onDone, onOpenRecording }: NeedsReviewDecisionProps) {
  const labels = me.tenant.labels;
  const headingId = useId();
  const noteId = useId();
  const toast = useToast();
  const recording = useRecording(recordingId);
  const rolesQuestion = recording.data?.status === "NEEDS_REVIEW" && recording.data.status_reason === UNCLEAR_ROLES;
  const speakers = useSpeakers(recordingId, rolesQuestion);
  const transcript = useTranscript(recordingId, rolesQuestion);
  const resolve = useResolveReview(recordingId);
  const [staff, setStaff] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const player = useSamplePlayer(transcript.data?.playback_url ?? undefined, async () => {
    const fresh = await transcript.refetch();
    return fresh.data?.playback_url ?? undefined;
  });

  const person = labels.person.toLowerCase();
  const thing = labels.recording.toLowerCase();
  const roleLabel = (role: string | null) =>
    role === null ? null : role === speakers.data?.choices[0] ? capitalise(labels.person) : capitalise(role);

  const decide = async (decision: Parameters<typeof resolve.mutateAsync>[0], done: string) => {
    try {
      await resolve.mutateAsync(decision);
      toast.show({ tone: "success", title: done, duration: 6000 });
      onDone();
    } catch (error) {
      toast.show({
        tone: "error",
        title: "That did not go through",
        message: error instanceof ApiError ? error.message : "Please try again.",
        requestId: error instanceof ApiError ? error.requestId : undefined,
      });
    }
  };

  const frame = "flex min-w-0 flex-col gap-5 rounded-panel border border-line bg-surface px-5 py-5 sm:px-6";
  if (recording.isError) {
    return (
      <section className={frame} aria-label="Review">
        <EmptyState icon={<Icon name="search" size={26} />} title={`We couldn't find this ${thing}`} />
      </section>
    );
  }
  if (!recording.data) {
    return (
      <section className={frame} aria-label="Review">
        <SkeletonGroup label="Loading the review" className="flex flex-col gap-3">
          <Skeleton className="h-8 w-72" />
          <Skeleton className="h-40 w-full" />
        </SkeletonGroup>
      </section>
    );
  }
  const r = recording.data;
  if (r.status !== "NEEDS_REVIEW") {
    return (
      <section className={frame} aria-label="Review">
        <EmptyState
          icon={<Icon name="reviews" size={26} />}
          title="This review is done"
          description={`The ${thing} is no longer waiting for review.`}
          action={<Button onClick={onOpenRecording}>Open the {thing}</Button>}
        />
      </section>
    );
  }

  const where = [
    r.person?.name,
    r.unit_name,
    `recorded ${formatWhen(r.recorded_at ?? r.created_at).replace(/^[TY]/, (c) => c.toLowerCase())}`,
  ]
    .filter(Boolean)
    .join(", ");
  const closeForm = (
    <div className="flex flex-col gap-2">
      <label htmlFor={noteId} className="text-sm font-semibold text-ink">
        Why is it not usable?
      </label>
      <textarea
        id={noteId}
        value={note}
        maxLength={500}
        rows={3}
        onChange={(e) => setNote(e.target.value)}
        placeholder="For example: the recorder was in a bag; nothing can be heard."
        className="rounded border border-line-input bg-surface px-3 py-2 text-ink placeholder:text-muted-2"
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="secondary"
          disabled={note.trim() === "" || resolve.isPending}
          onClick={() => void decide({ action: "close", note: note.trim() }, `The ${thing} was closed as not usable.`)}
        >
          Close as not usable
        </Button>
        <span className="text-small text-muted">It is marked failed with your note, and nothing is scored.</span>
      </div>
    </div>
  );

  return (
    <section aria-labelledby={headingId} className={frame}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-small text-muted">{rolesQuestion ? "Speakers" : "Needs review"}</span>
          <h2 id={headingId} className="m-0 text-2xl font-semibold tracking-tight">
            {rolesQuestion ? `Who is the ${person}?` : r.title}
          </h2>
          <p className="m-0 text-sm text-ink-2">
            {rolesQuestion ? `${r.title}. ` : ""}
            {where}
          </p>
        </div>
        <Button variant="secondary" onClick={onOpenRecording}>
          Open recording
        </Button>
      </header>

      <div className="flex items-start gap-3 rounded-card border border-warning-border bg-warning-surface px-4 py-3.5">
        <Icon name="alert" className="mt-0.5 shrink-0 text-warning-ink" />
        <div className="flex flex-col gap-0.5">
          <p className="m-0 font-semibold text-warning-ink">Why Sabha paused</p>
          <p className="m-0 text-ink-2">{r.status_note}</p>
        </div>
      </div>

      {rolesQuestion ? (
        <>
          <p className="m-0 text-ink-2">
            Listen to a few lines from each voice and choose the {person}. Sabha then scores the {thing} as usual. Only
            the {person} is scored.
          </p>
          {speakers.isPending ? (
            <Skeleton className="h-48 w-full" />
          ) : speakers.isError ? (
            <p className="m-0 text-danger">The voices could not be loaded. Please try again in a moment.</p>
          ) : (
            <>
              <ul className="m-0 grid list-none gap-3 p-0 xl:grid-cols-2" aria-label="Voices">
                {speakers.data.speakers.map((speaker, index) => (
                  <SpeakerCard
                    key={speaker.label}
                    speaker={speaker}
                    index={index}
                    chosen={staff === speaker.label}
                    onChoose={() => setStaff(speaker.label)}
                    guessLabel={roleLabel(speaker.guess)}
                    player={player}
                  />
                ))}
              </ul>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  disabled={staff === null || resolve.isPending}
                  onClick={() =>
                    void decide(
                      { action: "confirm_roles", staff_speaker: staff ?? "" },
                      `Thanks. Sabha is scoring the ${thing} now.`,
                    )
                  }
                >
                  {resolve.isPending ? "Saving…" : "Confirm and score"}
                </Button>
                <span className="text-small text-muted">
                  {staff === null
                    ? `Choose the voice of the ${person} first.`
                    : `Every other voice is treated as ${roleLabel(speakers.data.choices[1] ?? null)?.toLowerCase() ?? "the others"}.`}
                </span>
              </div>
            </>
          )}
          <details className="group border-t border-line-subtle pt-4">
            <summary className="flex min-h-touch cursor-pointer list-none items-center gap-1.5 text-sm font-semibold text-ink-2">
              <Icon name="chevronRight" size={16} className="transition-transform group-open:rotate-90" />
              Not usable? Close it instead
            </summary>
            <div className="pt-2">{closeForm}</div>
          </details>
        </>
      ) : (
        <>
          <p className="m-0 text-ink-2">
            Sabha cannot fix this by itself. If the {thing} cannot be scored, close it so it stops waiting.
          </p>
          {closeForm}
        </>
      )}
    </section>
  );
}
