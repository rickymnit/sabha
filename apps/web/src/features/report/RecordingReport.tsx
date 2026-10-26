// Recording report (P6.6), matching docs/design/02-recording-report.png and Analysis.dc.html. Reads an analysis
// payload (types.ts), the transcript (P6.5) and the recording's details; the route (/recordings/:id, P6.2) fetches
// them. Golden rule 5 is enforced here: only verified dimensions with quotes are ever rendered, whatever the
// payload contains.

import { useCallback, useId, useMemo, useRef, useState, type ReactNode } from "react";

import { Card, ScoreBar } from "../../design";
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
import { DealCardPanel } from "./DealCardPanel";
import { MeetingNotesPanel } from "./MeetingNotesPanel";
import { ReportHeader } from "./ReportHeader";
import { ReportMetrics } from "./ReportMetrics";
import { FailedState, NeedsReviewState, ProcessingState } from "./ReportStates";
import { ReportTimeline } from "./ReportTimeline";
import { TicketPanel } from "./TicketPanel";
import { VoicesPanel } from "./VoicesPanel";
import { DimensionDetail, RubricScoreList } from "./RubricPanels";
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
  rubricHref?: (rubric: AnalysisReport["rubric"]) => string;
  /** True when the viewer is the person analysed or their manager (decided by the API, P6.7). */
  canDispute?: boolean;
  /** Sends a dispute; required for the dispute button to open the dialog. */
  onSubmitDispute?: (draft: DisputeDraft) => Promise<void>;
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
  rubricHref,
  canDispute = false,
  onSubmitDispute,
  meeting,
}: RecordingReportProps) {
  const isReport = analysis.status === "completed" || analysis.status === "partial";
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <ReportHeader
        recording={recording}
        labels={labels}
        rubric={isReport ? analysis.rubric : undefined}
        rubricHref={rubricHref}
      />
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
          onSubmitDispute={canDispute ? onSubmitDispute : undefined}
          meeting={meeting}
        />
      )}
    </div>
  );
}

interface ReportBodyProps extends Omit<RecordingReportProps, "analysis" | "rubricHref" | "canDispute"> {
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
  onSubmitDispute,
  meeting,
}: ReportBodyProps) {
  const [disputeOpen, setDisputeOpen] = useState(false);
  const dimensions = useMemo(() => visibleDimensions(analysis.dimensions), [analysis.dimensions]);
  const notApplicable = notApplicableDimensions(analysis.dimensions);
  const hidden = analysis.dimensions.filter(
    (d) => !dimensions.includes(d as VerifiedDimension) && !notApplicable.some((n) => n.key === d.key),
  );
  const utterances = useMemo(() => transcript?.utterances ?? [], [transcript]);

  const [chosenKey, setChosenKey] = useState<string | null>(null);
  const selected =
    dimensions.find((d) => d.key === chosenKey) ?? dimensions.find((d) => d.key === defaultSelection(dimensions));

  const playerRef = useRef<AudioPlayerHandle>(null);
  const [currentMs, setCurrentMs] = useState<number | null>(null);
  // The player reports the new position through onTimeUpdate, which moves the playhead and transcript.
  const seek = useCallback((ms: number) => playerRef.current?.seek(ms), []);

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
  const timelineHeadingId = useId();
  const transcriptHeadingId = useId();
  const rubricLabel = `${analysis.rubric.name} v${analysis.rubric.version}`;

  return (
    <>
      <OverallPanel analysis={analysis} recording={recording} labels={labels} onSeek={seek} />

      {analysis.ticket && <TicketPanel ticket={analysis.ticket} onSeek={seek} />}

      {analysis.deal_card && <DealCardPanel card={analysis.deal_card} labels={labels} onSeek={seek} />}

      {analysis.meeting_notes && meeting && (
        <MeetingNotesPanel notes={analysis.meeting_notes} voiceName={meeting.voiceName} onSeek={seek} />
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

      <section
        aria-labelledby={timelineHeadingId}
        className="flex min-w-0 flex-col rounded-panel border border-line bg-surface px-5 pb-5 pt-4.5"
      >
        <ReportTimeline
          heading={
            <h2 id={timelineHeadingId} className="m-0 text-lg font-semibold">
              {labels.recording} timeline
            </h2>
          }
          player={
            <AudioPlayer
              ref={playerRef}
              label={`${labels.recording} audio`}
              getUrl={getPlaybackUrl}
              durationMs={recording.duration_ms}
              onTimeUpdate={setCurrentMs}
              showShortcutHint={false}
            />
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
        />
      </section>

      {analysis.metrics.length > 0 && <ReportMetrics metrics={analysis.metrics} onSeek={seek} />}

      {notApplicable.length > 0 && (
        <Card as="section" aria-label="Not applicable" data-testid="not-applicable-note">
          <p className="m-0 text-sm font-semibold text-ink">Not applicable to this {labels.recording.toLowerCase()}</p>
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

      <div className="flex flex-wrap items-start gap-5">
        <RubricScoreList dimensions={dimensions} selectedKey={selected?.key ?? null} onSelect={setChosenKey} />
        {selected && (
          <DimensionDetail
            dimension={selected}
            speakers={speakers}
            onSeek={seek}
            provenance={
              // The model id means nothing to most readers; administrators see it for support questions.
              viewerRole === "admin"
                ? `Scored against the ${rubricLabel} rubric by ${analysis.model.ids.join(", ")}`
                : `Scored against the ${rubricLabel} rubric`
            }
            onDispute={onSubmitDispute ? () => setDisputeOpen(true) : undefined}
          />
        )}
      </div>
      {onSubmitDispute && (
        <DisputeDialog
          open={disputeOpen}
          dimensions={dimensions.map((d) => ({ key: d.key, name: d.name, score: displayedScore(d) }))}
          initialKey={selected?.key}
          onSubmit={onSubmitDispute}
          onClose={() => setDisputeOpen(false)}
        />
      )}

      {transcript && (
        <section
          aria-labelledby={transcriptHeadingId}
          className="min-w-0 overflow-hidden rounded-panel border border-line bg-surface"
        >
          <div className="border-b border-line-subtle px-5 py-3.5">
            <h2 id={transcriptHeadingId} className="m-0 text-lg font-semibold">
              Transcript
            </h2>
          </div>
          <TranscriptList
            utterances={utterances}
            roles={roles}
            currentMs={currentMs}
            onSeek={seek}
            highlights={highlights}
            label={`Transcript of the ${recordingWord}`}
            height="min(60vh, 480px)"
          />
        </section>
      )}
    </>
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
  let comparisonText: ReactNode = null;
  if (overall !== null && comparison && Number.isFinite(comparison.median)) {
    const median = formatScore(comparison.median);
    const [text, tone] =
      overall < comparison.median
        ? [`Below the ${comparison.scope} median of ${median}`, "text-warning"]
        : overall > comparison.median
          ? [`Above the ${comparison.scope} median of ${median}`, "text-success"]
          : [`Level with the ${comparison.scope} median of ${median}`, "text-muted"];
    comparisonText = (
      <span data-testid="overall-comparison" className={`text-sm font-medium ${tone}`}>
        {text}
      </span>
    );
  }
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-wrap overflow-hidden rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-[1_1_220px] flex-col gap-1.5 border-b border-line-subtle bg-surface-faint px-6 py-[22px] sm:border-b-0 sm:border-r">
        <span className="text-sm text-muted">Overall score</span>
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
        {overall !== null && <ScoreBar score={overall} hideValue className="mt-1" />}
        {comparisonText}
        <span data-testid="overall-checked" className="text-small text-muted">
          {checkedText(analysis.dimensions)}
        </span>
        {history && history.count > 0 && (
          <span data-testid="overall-history" className="text-small text-muted">
            {recording.person.name}’s last {history.count} {labels.recording_plural.toLowerCase()}:{" "}
            {formatScore(history.min)} to {formatScore(history.max)}
          </span>
        )}
      </div>
      <div className="flex min-w-0 flex-[999_1_420px] flex-col gap-3 px-6 py-[22px]">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          Summary
        </h2>
        <p className="m-0 max-w-[72ch] text-ink-2">{analysis.summary}</p>
        {analysis.suggestions.length > 0 && (
          <div className="flex flex-col gap-2">
            <h3 className="m-0 text-sm font-semibold">Suggestions for the next {labels.recording.toLowerCase()}</h3>
            <ol className="m-0 flex max-w-[76ch] list-decimal flex-col gap-1.5 pl-5 text-ink-2">
              {analysis.suggestions.map((s, i) => (
                <li key={`${s.utterance_id}-${i}`}>
                  <button
                    type="button"
                    onClick={() => onSeek(s.start_ms)}
                    className="font-semibold text-primary hover:text-primary-hover hover:underline"
                  >
                    <span className="sr-only">Play from </span>
                    {formatClock(s.start_ms)}
                  </button>{" "}
                  {s.text}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </section>
  );
}
