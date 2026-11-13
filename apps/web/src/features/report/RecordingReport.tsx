// Recording report (P6.6), matching docs/design/02-recording-report.png and Analysis.dc.html. Reads an analysis
// payload (types.ts), the transcript (P6.5) and the recording's details; the route (/recordings/:id, P6.2) fetches
// them. Golden rule 5 is enforced here: only verified dimensions with quotes are ever rendered, whatever the
// payload contains.

import { PrivateCoachingNote } from "./PrivateCoachingNote";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import { Card, Tabs, cx, scoreBand } from "../../design";

const BAND_FILL = { low: "bg-danger-bar", mid: "bg-warning-bar", good: "bg-success-bar" } as const;
import {
  AudioPlayer,
  TranscriptList,
  formatClock,
  lineAt,
  type AudioPlayerHandle,
  type PlaybackUrl,
  type RoleLabels,
  type Transcript,
} from "../transcript";
import { checkedText, formatScore, joinList } from "./format";
import { CaseCardPanel } from "./CaseCardPanel";
import { DealCardPanel } from "./DealCardPanel";
import { MeetingNotesPanel } from "./MeetingNotesPanel";
import { ReportAnswer } from "./ReportAnswer";
import { ReportHeader } from "./ReportHeader";
import { ReportMetrics } from "./ReportMetrics";
import { FailedState, NeedsReviewState, ProcessingState } from "./ReportStates";
import { ReportTimeline } from "./ReportTimeline";
import { PlayingFromContext, SeekModeContext, usePlayingFrom } from "./seekMode";
import { SmallPauseIcon } from "./icons";
import { TicketPanel } from "./TicketPanel";
import { VoicesPanel } from "./VoicesPanel";
import { RubricAccordion } from "./RubricPanels";
import { NextTimePanel } from "./NextTimePanel";
import { NextStepCard, SalesOverall, TalkListenCard } from "./SalesPanels";
import { evidenceLines } from "./timeline";
import { notApplicableDimensions, visibleDimensions } from "./visibility";
import { DisputeDialog } from "../disputes/DisputeDialog";
import type { DisputeDraft } from "../disputes/types";
import {
  displayedScore,
  type AnalysisPayload,
  type AnalysisReport,
  type Labels,
  type ReportRecording,
  type VerifiedDimension,
  type ViewerRole,
} from "./types";

/** The lowest score first catches the eye in the design (Analysis.dc.html:273); ties keep rubric order. */
function defaultSelection(dimensions: readonly VerifiedDimension[]): string | null {
  let best: VerifiedDimension | undefined;
  for (const d of dimensions) if (!best || d.score < best.score) best = d;
  return best?.key ?? null;
}

export interface RecordingReportProps {
  recording: ReportRecording;
  analysis: AnalysisPayload;
  /** null while the transcript is not available (processing, failed). */
  transcript: Transcript | null;
  labels: Labels;
  /** Role keys to labels, from the tenant's labels dictionary. */
  roles: RoleLabels;
  viewerRole: ViewerRole;
  /** Presigned playback URL for the audio player (P6.5). */
  getPlaybackUrl: () => Promise<PlaybackUrl>;
  /** Shown instead of the player once retention deleted the audio (P7.3); the transcript stays. */
  audioNote?: string;
  rubricHref?: (rubric: AnalysisReport["rubric"]) => string;
  /** True when the viewer is the person analysed or their manager (decided by the API, P6.7). */
  canDispute?: boolean;
  /** Sends a dispute; required for the dispute button to open the dialog. */
  onSubmitDispute?: (draft: DisputeDraft) => Promise<void>;
  /** Buttons under the header (the "…" menu). */
  actions?: ReactNode;
  /** Above the report: the coaching steps (managers) or the manager's note (the person analysed). */
  banner?: ReactNode;
  /** The rubric's level descriptions for a dimension, for "where this lesson is" and the next level. */
  levels?: (key: string) => readonly { level: number; description: string }[] | undefined;
  /** The dispute button's words: "Dispute this score" for the person analysed. */
  disputeLabel?: string;
  /** Sales: the rubric's words for the interest levels. */
  interestLabels?: Record<string, string>;
  /** Open at this moment (ms, original timeline): the transcript goes to that line; nothing plays by itself. */
  startAtMs?: number;
  /** Meetings: the voices in order of first speech, their names, and saving new names. */
  meeting?: {
    voices: string[];
    names: Record<string, string>;
    voiceName: (voice: string) => string;
    onSaveNames: (names: Record<string, string>) => Promise<void>;
  };
}

export function RecordingReport({
  recording,
  analysis,
  transcript,
  labels,
  roles,
  viewerRole,
  getPlaybackUrl,
  audioNote,
  rubricHref,
  canDispute = false,
  onSubmitDispute,
  meeting,
  actions,
  banner,
  levels,
  disputeLabel,
  interestLabels,
  startAtMs,
}: RecordingReportProps) {
  const isReport = analysis.status === "completed" || analysis.status === "partial";
  const disputed = isReport
    ? analysis.dimensions.filter((d) => d.verified && (d as VerifiedDimension).dispute_open).length
    : 0;
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <ReportHeader
        recording={recording}
        labels={labels}
        rubric={isReport ? analysis.rubric : undefined}
        rubricHref={rubricHref}
        actions={actions}
        disputed={disputed}
      />
      {isReport && banner}
      {analysis.status === "processing" && <ProcessingState analysis={analysis} labels={labels} />}
      {analysis.status === "failed" && <FailedState analysis={analysis} labels={labels} />}
      {analysis.status === "needs_review" && <NeedsReviewState analysis={analysis} labels={labels} />}
      {(analysis.status === "completed" || analysis.status === "partial") && (
        <ReportBody
          recording={recording}
          analysis={analysis}
          transcript={transcript}
          labels={labels}
          roles={roles}
          viewerRole={viewerRole}
          getPlaybackUrl={getPlaybackUrl}
          audioNote={audioNote}
          onSubmitDispute={canDispute ? onSubmitDispute : undefined}
          meeting={meeting}
          levels={levels}
          interestLabels={interestLabels}
          startAtMs={startAtMs}
          disputeLabel={disputeLabel}
        />
      )}
    </div>
  );
}

interface ReportBodyProps extends Omit<
  RecordingReportProps,
  "analysis" | "rubricHref" | "canDispute" | "actions" | "banner"
> {
  analysis: AnalysisReport;
}

function ReportBody({
  recording,
  analysis,
  transcript,
  labels,
  roles,
  viewerRole,
  getPlaybackUrl,
  audioNote,
  onSubmitDispute,
  meeting,
  levels,
  disputeLabel,
  interestLabels,
  startAtMs,
}: ReportBodyProps) {
  const [disputeOpen, setDisputeOpen] = useState(false);
  const [tab, setTab] = useState<"why" | "listen">("why");
  const rubricRef = useRef<HTMLDivElement>(null);
  const dimensions = useMemo(() => visibleDimensions(analysis.dimensions), [analysis.dimensions]);
  const notApplicable = notApplicableDimensions(analysis.dimensions);
  const hidden = analysis.dimensions.filter(
    (d) => !dimensions.includes(d as VerifiedDimension) && !notApplicable.some((n) => n.key === d.key),
  );
  const utterances = useMemo(() => transcript?.utterances ?? [], [transcript]);

  // The open rubric row; the lowest score is open at first. Closing every row keeps the last one's pins.
  const [chosenKey, setChosenKey] = useState<string | null | undefined>(undefined);
  const openKey = chosenKey === undefined ? defaultSelection(dimensions) : chosenKey;
  const [pinKey, setPinKey] = useState<string | null>(null);
  const selected =
    dimensions.find((d) => d.key === openKey) ??
    dimensions.find((d) => d.key === pinKey) ??
    dimensions.find((d) => d.key === defaultSelection(dimensions));

  const playerRef = useRef<AudioPlayerHandle>(null);
  const transcriptRef = useRef<HTMLElement>(null);
  const [currentMs, setCurrentMs] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  // The time last asked for: asking for it again while it plays pauses, and once more carries on.
  const [lastSeek, setLastSeek] = useState<number | null>(null);
  // With audio, the player reports the new position through onTimeUpdate, which moves the playhead and transcript.
  // Without (an uploaded transcript, or deleted audio), a time goes straight to its line in the transcript.
  const noAudio = Boolean(audioNote);
  const seek = useCallback(
    (ms: number) => {
      if (!noAudio) {
        const player = playerRef.current;
        if (player && ms === lastSeek) {
          if (playing) player.pause();
          else player.play();
          return;
        }
        setLastSeek(ms);
        player?.seek(ms);
        return;
      }
      setCurrentMs(ms);
      transcriptRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    [noAudio, lastSeek, playing, setCurrentMs],
  );

  // A link to a moment (?at= from the rep's interaction page): show that line once, without playing.
  const startedAt = useRef(false);
  useEffect(() => {
    if (startAtMs === undefined || startedAt.current) return;
    startedAt.current = true;
    setTab("listen");
    setCurrentMs(startAtMs);
    requestAnimationFrame(() => transcriptRef.current?.scrollIntoView({ block: "start" }));
  }, [startAtMs]);

  const highlights = useMemo(
    () => (selected ? evidenceLines(utterances, selected.evidence) : new Map<number, number[]>()),
    [utterances, selected],
  );
  const speakers = useMemo(
    () =>
      (selected?.evidence ?? []).map((e) => {
        const u = utterances[lineAt(utterances, e.start_ms)];
        return u ? (roles[u.role]?.label ?? u.speaker_label) : undefined;
      }),
    [utterances, selected, roles],
  );

  const recordingWord = labels.recording.toLowerCase();
  // Sales conversations get the UI v2 sales layout (PDF pages 5 and 9): points lost, the deal at a glance, the next
  // step and talk and listen beside the transcript.
  const sales = analysis.rubric.id.startsWith("sales.") || Boolean(analysis.deal_card);
  const repName = recording.person.name.split(" ")[0] ?? recording.person.name;
  const timelineHeadingId = useId();
  const transcriptHeadingId = useId();
  const rubricLabel = `${analysis.rubric.name} v${analysis.rubric.version}`;

  const transcriptPanel = transcript && (
    <section
      ref={transcriptRef}
      aria-labelledby={transcriptHeadingId}
      className="min-w-0 overflow-hidden rounded-panel border border-line bg-surface lg:sticky lg:top-4"
    >
      <div className="flex items-baseline justify-between gap-2 border-b border-line-subtle px-5 py-3.5">
        <h2 id={transcriptHeadingId} className="m-0 text-lg font-semibold">
          Transcript
        </h2>
        {recording.languages.length > 0 && (
          <span className="text-small text-muted">{joinList(recording.languages)}</span>
        )}
      </div>
      <TranscriptList
        utterances={utterances}
        roles={roles}
        currentMs={currentMs}
        onSeek={seek}
        highlights={highlights}
        label={`Transcript of the ${recordingWord}`}
        height="min(70vh, 720px)"
        followJumps={noAudio}
        compact
      />
    </section>
  );

  // Details sit in two tabs under the answer; both stay mounted so the audio keeps playing. With audio a quote's time
  // plays right there (its own button pauses it); without, it can only be shown in the transcript, so that tab opens.
  const listen = (ms: number) => {
    if (noAudio) setTab("listen");
    seek(ms);
  };
  const why = (key: string) => {
    setTab("why");
    setPinKey(key);
    setChosenKey(key);
    requestAnimationFrame(() => rubricRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const whyPanel = (
    <div
      className={cx(
        "grid items-start gap-5",
        sales ? "lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]" : "max-w-[960px]",
      )}
    >
      <div className="flex min-w-0 flex-col gap-5">
        {/* The answer above has the score and summary; this panel stays only for the person's own coaching. */}
        {!analysis.coaching_private &&
          (sales ? (
            <>
              <SalesOverall analysis={analysis} recording={recording} labels={labels} onSeek={listen} />
              {analysis.next_time && <NextTimePanel coaching={analysis.next_time} onSeek={listen} />}
            </>
          ) : (
            <OverallPanel analysis={analysis} recording={recording} labels={labels} onSeek={listen} />
          ))}

        {analysis.ticket && <TicketPanel ticket={analysis.ticket} onSeek={listen} />}

        {analysis.deal_card && !sales && <DealCardPanel card={analysis.deal_card} labels={labels} onSeek={listen} />}

        {analysis.case_card && <CaseCardPanel card={analysis.case_card} onSeek={listen} />}

        {analysis.meeting_notes && meeting && (
          <MeetingNotesPanel notes={analysis.meeting_notes} voiceName={meeting.voiceName} onSeek={listen} />
        )}

        {meeting && transcript && (
          <VoicesPanel
            key={JSON.stringify(meeting.names)}
            transcript={transcript}
            voices={meeting.voices}
            names={meeting.names}
            onSave={meeting.onSaveNames}
          />
        )}

        {notApplicable.length > 0 && (
          <Card as="section" aria-label="Not applicable" data-testid="not-applicable-note">
            <p className="m-0 text-sm font-semibold text-ink">
              Not applicable to this {labels.recording.toLowerCase()}
            </p>
            {notApplicable.map((d) => (
              <p key={d.key} className="m-0 text-ink-2">
                <span className="font-semibold">{d.name}:</span> {d.rationale} It is left out of the overall score.
              </p>
            ))}
          </Card>
        )}

        {viewerRole === "admin" && hidden.length > 0 && (
          <Card as="section" tone="warning" aria-label="Hidden dimensions" data-testid="admin-hidden-note">
            <p className="m-0 text-sm font-semibold text-warning-ink">Visible to admins only</p>
            <p className="m-0 text-ink-2">
              {hidden.length === 1 ? "1 dimension is" : `${hidden.length} dimensions are`} hidden because their quotes
              could not be verified in the transcript: {joinList(hidden.map((d) => d.name))}.{" "}
              {hidden.length === 1 ? "It is" : "They are"} left out of the overall score.
            </p>
            {analysis.reasons.map((r, i) => (
              <p key={i} className="m-0 text-caption text-muted">
                {r.message} ({r.code})
              </p>
            ))}
          </Card>
        )}

        <div ref={rubricRef} className="scroll-mt-4" />
        <RubricAccordion
          dimensions={dimensions}
          openKey={openKey}
          onToggle={(key) => {
            setPinKey(key);
            setChosenKey(openKey === key ? null : key);
          }}
          speakers={speakers}
          onSeek={listen}
          // The model id means nothing to most readers; administrators find it under Technical details.
          provenance={`Scored against the ${rubricLabel} rubric`}
          levels={levels}
          disputeLabel={disputeLabel}
          recordingWord={recordingWord}
          onDispute={onSubmitDispute ? () => setDisputeOpen(true) : undefined}
          pointsLost={sales}
          overall={analysis.overall}
        />
        {onSubmitDispute && (
          <DisputeDialog
            open={disputeOpen}
            dimensions={dimensions
              .filter((d) => !d.dispute_open)
              .map((d) => ({ key: d.key, name: d.name, score: displayedScore(d) }))}
            initialKey={selected?.key}
            onSubmit={onSubmitDispute}
            onClose={() => setDisputeOpen(false)}
          />
        )}

        {sales && analysis.deal_card && (
          <DealCardPanel card={analysis.deal_card} labels={labels} onSeek={listen} interestLabels={interestLabels} />
        )}

        {!sales && analysis.metrics.length > 0 && <ReportMetrics metrics={analysis.metrics} onSeek={listen} />}
      </div>
      {sales && (
        <div className="flex min-w-0 flex-col gap-5">
          {analysis.deal_card && <NextStepCard step={analysis.deal_card.next_step} repName={repName} onSeek={listen} />}
          <TalkListenCard metrics={analysis.metrics} labels={labels} repName={repName} onSeek={listen} />
        </div>
      )}
    </div>
  );

  const listenPanel = (
    <div className="flex flex-col gap-5">
      <section
        aria-labelledby={timelineHeadingId}
        className="flex min-w-0 flex-col rounded-panel border border-line bg-surface px-5 pb-5 pt-4.5"
      >
        <ReportTimeline
          heading={
            <h2 id={timelineHeadingId} className="m-0 text-lg font-semibold">
              Who spoke when
            </h2>
          }
          player={
            audioNote ? (
              <p className="m-0 rounded border border-line-subtle bg-surface-subtle px-3 py-2 text-sm text-muted">
                {audioNote}
              </p>
            ) : (
              <AudioPlayer
                ref={playerRef}
                label={`${labels.recording} audio`}
                getUrl={getPlaybackUrl}
                durationMs={recording.duration_ms}
                onTimeUpdate={setCurrentMs}
                onPlayingChange={setPlaying}
                showShortcutHint={false}
              />
            )
          }
          utterances={utterances}
          roles={roles}
          durationMs={recording.duration_ms}
          removedSilence={recording.removed_silence}
          phases={analysis.phases}
          evidence={selected?.evidence ?? []}
          dimensionName={selected?.name}
          currentMs={currentMs}
          onSeek={seek}
          recordingWord={recordingWord}
        />
      </section>
      {transcriptPanel}
    </div>
  );

  return (
    <SeekModeContext.Provider value={noAudio ? "go" : "play"}>
      <PlayingFromContext.Provider value={playing && !noAudio ? lastSeek : null}>
        <ReportAnswer
          analysis={analysis}
          dimensions={dimensions}
          labels={labels}
          onWhy={why}
          onSeek={listen}
          personName={recording.person.name}
        />
        <Tabs
          label="Report details"
          value={tab}
          onChange={setTab}
          keepMounted
          tabs={[
            { value: "why", label: "Why this score", panel: whyPanel },
            { value: "listen", label: transcript ? "Listen and read" : "Listen", panel: listenPanel },
          ]}
        />
      </PlayingFromContext.Provider>
    </SeekModeContext.Provider>
  );
}

function OverallPanel({
  analysis,
  recording,
  labels,
  onSeek,
}: {
  analysis: AnalysisReport;
  recording: ReportRecording;
  labels: Labels;
  onSeek: (ms: number) => void;
}) {
  const headingId = useId();
  const { overall, comparison, person_history: history } = analysis;
  const median = comparison && Number.isFinite(comparison.median) ? comparison.median : null;
  const scope = comparison ? comparison.scope.charAt(0).toUpperCase() + comparison.scope.slice(1) : "";
  const band = overall === null ? "mid" : scoreBand(overall);
  const firstName = recording.person.name.split(" ")[0] ?? recording.person.name;
  const playingFrom = usePlayingFrom();
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-wrap overflow-hidden rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-[1_1_200px] flex-col gap-1.5 border-b border-line-subtle bg-surface-faint px-6 py-5 sm:border-b-0 sm:border-r">
        <span className="text-sm text-muted">Overall</span>
        {overall === null ? (
          <>
            <span className="text-hero font-semibold text-muted-2">
              <span aria-hidden="true">—</span>
              <span className="sr-only">No overall score</span>
            </span>
            <span className="text-small text-muted">Too few dimensions could be verified for an overall score.</span>
          </>
        ) : (
          <span className="text-hero font-semibold" data-testid="overall-score">
            {formatScore(overall)}
            <span className="text-xl font-medium tracking-normal text-muted-2">
              <span aria-hidden="true"> / 5</span>
              <span className="sr-only"> out of 5</span>
            </span>
          </span>
        )}
        {overall !== null && (
          <div className="relative mt-1 pb-5" aria-hidden="true">
            <div className="h-1.5 overflow-hidden rounded-full bg-track">
              <div
                className={cx("h-full rounded-full", BAND_FILL[band])}
                style={{ width: `${(overall / 5) * 100}%` }}
              />
            </div>
            {median !== null && (
              <>
                <span className="absolute -top-1 h-3.5 w-0.5 bg-ink" style={{ left: `${(median / 5) * 100}%` }} />
                <span
                  className="absolute top-3 -translate-x-1/2 whitespace-nowrap text-caption text-muted"
                  style={{ left: `${Math.min(80, Math.max(20, (median / 5) * 100))}%` }}
                >
                  {scope} median {formatScore(median)}
                </span>
              </>
            )}
          </div>
        )}
        {overall !== null && median !== null && (
          <span data-testid="overall-comparison" className="sr-only">
            {scope} median {formatScore(median)}
          </span>
        )}
        {history && history.count > 0 && (
          <span data-testid="overall-history" className="text-small text-muted">
            {history.count === 1
              ? `${firstName}’s previous ${labels.recording.toLowerCase()}: ${formatScore(history.min)}.`
              : `${firstName}’s last ${history.count === 5 ? "five" : history.count} ${labels.recording_plural.toLowerCase()}: ${formatScore(history.min)} to ${formatScore(history.max)}.`}
          </span>
        )}
        <span data-testid="overall-checked" className="text-caption text-muted-2">
          {checkedText(analysis.dimensions)}
        </span>
      </div>
      <div className="flex min-w-0 flex-[999_1_380px] flex-col gap-3 px-6 py-5">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          What happened in this {labels.recording.toLowerCase()}
        </h2>
        <p className="m-0 max-w-[72ch] text-ink-2">{analysis.summary}</p>
        {analysis.coaching_private && <PrivateCoachingNote firstName={firstName} />}
        {analysis.suggestions.length > 0 && (
          <ul
            aria-label={`Suggestions for the next ${labels.recording.toLowerCase()}`}
            className="m-0 flex list-none flex-col gap-2 p-0"
          >
            {analysis.suggestions.map((s, i) => (
              <li key={`${s.utterance_id}-${i}`} className="flex items-start gap-3 text-ink-2">
                <button
                  type="button"
                  onClick={() => onSeek(s.start_ms)}
                  className="min-w-[54px] shrink-0 rounded-md border border-primary-border bg-primary-tint-subtle px-2 py-1 text-center text-small font-semibold tabular-nums text-primary-hover hover:bg-primary-tint"
                >
                  <span className="sr-only">{playingFrom === s.start_ms ? "Pause, playing from " : "Play from "}</span>
                  {playingFrom === s.start_ms && (
                    <span className="mr-1 inline-flex align-[-1px]">
                      <SmallPauseIcon />
                    </span>
                  )}
                  {formatClock(s.start_ms)}
                </button>
                <span className="pt-0.5">{s.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
