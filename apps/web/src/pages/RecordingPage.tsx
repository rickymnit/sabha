// /recordings/:id (P6.2, P6.5, P6.6): the recording report on the real API. Three reads in parallel: the
// recording's details, the report payload for its current state, and (once there is one) the transcript with a
// playback URL. While the recording is processing, the page refreshes itself (api/hooks.ts).

import { useCallback } from "react";
import { useOutletContext, useParams } from "react-router-dom";

import { useAnalysis, useApi, useRecording, useTranscript } from "../api/hooks";
import type { Me, TranscriptResponse } from "../api/types";
import { EmptyState, Skeleton, SkeletonGroup } from "../design";
import { RecordingReport } from "../features/report";
import type { PlaybackUrl } from "../features/transcript";
import { viewerRole } from "../app/format";
import { reportRecording, roleLabels } from "./recordingView";

export function RecordingPage() {
  const me = useOutletContext<Me>();
  const { id = "" } = useParams();
  const api = useApi();
  const recording = useRecording(id);
  const analysis = useAnalysis(id);
  const hasTranscript = analysis.data !== undefined && analysis.data.status !== "processing";
  const transcript = useTranscript(id, hasTranscript || recording.data?.status === "ANALYZING");

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
  return (
    <RecordingReport
      recording={reportRecording(recording.data)}
      analysis={analysis.data}
      transcript={data?.transcript ?? null}
      labels={me.tenant.labels}
      roles={roleLabels(data?.roles ?? {}, me.tenant.labels.person)}
      viewerRole={viewerRole(me.user.role)}
      getPlaybackUrl={getPlaybackUrl}
    />
  );
}
