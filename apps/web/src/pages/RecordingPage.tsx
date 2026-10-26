// /recordings/:id (P6.2, P6.5, P6.6): the recording report on the real API. Three reads in parallel: the
// recording's details, the report payload for its current state, and (once there is one) the transcript with a
// playback URL. While the recording is processing, the page refreshes itself (api/hooks.ts).

import { useCallback, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import {
  useAnalysis,
  useAnalysisHistory,
  useApi,
  useRaiseDispute,
  useReanalyse,
  useRecording,
  useTranscript,
} from "../api/hooks";
import { useSession } from "../session/session";
import type { Me, TranscriptResponse } from "../api/types";
import { Button, EmptyState, Skeleton, SkeletonGroup, useToast } from "../design";
import type { DisputeDraft } from "../features/disputes/types";
import { ReanalyseDialog, VersionPicker, versionLabel } from "../features/reanalysis";
import { RecordingReport } from "../features/report";
import type { PlaybackUrl } from "../features/transcript";
import { viewerRole } from "../app/format";
import { RESOLVERS } from "../app/nav";
import { meetingView, reportRecording, roleLabels, voiceLabel } from "./recordingView";

export function RecordingPage() {
  const me = useOutletContext<Me>();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const api = useApi();
  const { token } = useSession();
  const recording = useRecording(id);
  const [version, setVersion] = useState<string | undefined>(undefined); // an earlier analysis, or the latest
  const [reanalysing, setReanalysing] = useState(false);
  const analysis = useAnalysis(id, version);
  const history = useAnalysisHistory(id, recording.data?.status === "COMPLETED");
  const reanalyse = useReanalyse(id);
  const hasTranscript = analysis.data !== undefined && analysis.data.status !== "processing";
  const transcript = useTranscript(id, hasTranscript || recording.data?.status === "ANALYZING");
  const raise = useRaiseDispute(id);
  const toast = useToast();
  const analysisId = analysis.data && "analysis_id" in analysis.data ? analysis.data.analysis_id : undefined;
  const submitDispute = useCallback(
    async (draft: DisputeDraft) => {
      if (!analysisId) return;
      await raise.mutateAsync({ analysisId, draft });
      toast.show({
        tone: "success",
        title: "Dispute sent",
        message: "A reviewer will look at this score. You will get an email when it is decided.",
        duration: 6_000,
      });
    },
    [analysisId, raise, toast],
  );

  const getPlaybackUrl = useCallback(async (): Promise<PlaybackUrl> => {
    // A fresh URL each time: they expire after PLAYBACK_URL_EXPIRY_S, and issuing one is audited.
    const fresh = await api<TranscriptResponse>(`/v1/recordings/${encodeURIComponent(id)}/transcript`);
    const expires = new Date(Date.now() + fresh.playback_expires_in_s * 1000).toISOString();
    return { url: fresh.playback_url, expires_at: expires };
  }, [api, id]);

  if (recording.isError || analysis.isError) {
    const error = recording.error ?? analysis.error;
    return (
      <EmptyState
        title={error?.status === 404 ? "Not found" : "Could not load this page"}
        description={error?.message}
      />
    );
  }
  if (!recording.data || !analysis.data) {
    return (
      <SkeletonGroup label="Loading the report" className="flex flex-col gap-3">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-64 w-full" />
      </SkeletonGroup>
    );
  }
  const data = transcript.data ?? null;
  const isMeeting = recording.data.type === "meeting";
  const view = isMeeting && data ? meetingView(data.transcript, recording.data.voice_names) : null;
  const meeting = view
    ? {
        voices: view.voices,
        names: recording.data.voice_names,
        voiceName: (voice: string) => voiceLabel(voice, view.voices, recording.data.voice_names),
        onSaveNames: async (names: Record<string, string>) => {
          await apiFetch(`/v1/recordings/${encodeURIComponent(id)}/voices`, { method: "PUT", token, body: { names } });
          await recording.refetch();
        },
      }
    : undefined;
  // A meeting has an organiser, not a person analysed (ADR 0008).
  const labels = isMeeting ? { ...me.tenant.labels, person: "Organiser" } : me.tenant.labels;
  const canReview = recording.data.status === "NEEDS_REVIEW" && RESOLVERS.includes(me.user.role);
  const versions = history.data ?? [];
  const shownVersion = version ? versions.find((v) => v.id === version) : undefined;
  const isAdmin = me.user.role === "owner" || me.user.role === "admin";
  const canReanalyse = isAdmin && recording.data.status === "COMPLETED" && !version;
  const recordingWord = me.tenant.labels.recording.toLowerCase();
  return (
    <div className="flex flex-col gap-4">
      {canReview && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-warning-border bg-warning-surface px-4 py-3">
          <span className="text-ink-2">
            This {me.tenant.labels.recording.toLowerCase()} is waiting for your review.
          </span>
          <Button onClick={() => navigate(`/reviews/${id}`)}>Review it</Button>
        </div>
      )}
      {(versions.length > 1 || canReanalyse) && (
        <div className="flex flex-wrap items-center justify-end gap-3">
          <VersionPicker versions={versions} selected={version} onSelect={setVersion} />
          {canReanalyse && (
            <Button variant="secondary" onClick={() => setReanalysing(true)}>
              Re-analyse
            </Button>
          )}
        </div>
      )}
      {shownVersion && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line-subtle bg-surface-subtle px-4 py-3">
          <span className="text-ink-2">
            You are looking at an earlier analysis ({versionLabel(shownVersion, false)}). Its numbers no longer count in
            trends.
          </span>
          <Button variant="secondary" onClick={() => setVersion(undefined)}>
            Show the latest
          </Button>
        </div>
      )}
      {reanalysing && (
        <ReanalyseDialog
          recordingWord={recordingWord}
          onSubmit={async (reason) => {
            await reanalyse.mutateAsync(reason);
            toast.show({
              tone: "success",
              title: "Re-analysis started",
              message: `The new report will appear here in a few minutes. The current one stays as an earlier version.`,
              duration: 6_000,
            });
          }}
          onClose={() => setReanalysing(false)}
        />
      )}
      <RecordingReport
        recording={reportRecording(recording.data)}
        analysis={analysis.data}
        transcript={view?.transcript ?? data?.transcript ?? null}
        labels={labels}
        roles={view?.roles ?? roleLabels(data?.roles ?? {}, me.tenant.labels.person)}
        viewerRole={viewerRole(me.user.role)}
        getPlaybackUrl={getPlaybackUrl}
        meeting={meeting}
        canDispute={"can_dispute" in analysis.data && analysis.data.can_dispute === true}
        onSubmitDispute={submitDispute}
      />
    </div>
  );
}
