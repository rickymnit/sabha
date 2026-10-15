// Demo of the recording report (P6.6), served at /dev/report in development only (see main.tsx).
// Mock analysis built on the P6.5 mock transcript, and audio synthesised in the browser; the real page reads
// GET /v1/recordings/{id}/analysis and /transcript.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SegmentedControl } from "../design";
import { RecordingReport, type AnalysisPayload, type ViewerRole } from "../features/report";
import { mockFailed, mockLesson, mockNeedsReview, mockProcessing, mockReport } from "../features/report/mock";
import type { PlaybackUrl } from "../features/transcript";
import { synthesizeWav } from "./synthAudio";

type DemoState = "completed" | "no-comparison" | "partial" | "processing" | "needs-review" | "failed";

const STATES: { value: DemoState; label: string }[] = [
  { value: "completed", label: "Completed" },
  { value: "no-comparison", label: "No comparison" },
  { value: "partial", label: "Partial" },
  { value: "processing", label: "Processing" },
  { value: "needs-review", label: "Needs review" },
  { value: "failed", label: "Failed" },
];

const ROLES: { value: ViewerRole; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "manager", label: "Manager" },
  { value: "staff", label: "Staff" },
];

const URL_LIFETIME_MS = 10 * 60_000;

export interface ReportDemoProps {
  initialState?: DemoState;
  initialViewerRole?: ViewerRole;
}

export default function ReportDemo({ initialState = "completed", initialViewerRole = "admin" }: ReportDemoProps) {
  const lesson = useMemo(() => mockLesson(), []);
  const [state, setState] = useState<DemoState>(initialState);
  const [viewerRole, setViewerRole] = useState<ViewerRole>(initialViewerRole);

  const analysis: AnalysisPayload = useMemo(() => {
    switch (state) {
      case "processing":
        return mockProcessing(lesson);
      case "needs-review":
        return mockNeedsReview(lesson);
      case "failed":
        return mockFailed(lesson);
      default:
        return mockReport(lesson, state);
    }
  }, [lesson, state]);

  const blob = useMemo(
    () => synthesizeWav(lesson.transcript.utterances, { durationMs: lesson.recording.duration_ms, sampleRate: 3000 }),
    [lesson],
  );
  const urlsRef = useRef<string[]>([]);
  useEffect(
    () => () => {
      urlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      urlsRef.current = [];
    },
    [blob],
  );
  const getPlaybackUrl = useCallback(async (): Promise<PlaybackUrl> => {
    const url = URL.createObjectURL(blob);
    urlsRef.current.push(url);
    while (urlsRef.current.length > 2) URL.revokeObjectURL(urlsRef.current.shift() as string);
    return { url, expires_at: new Date(Date.now() + URL_LIFETIME_MS).toISOString() };
  }, [blob]);

  const hasTranscript = state !== "processing" && state !== "failed";

  return (
    <main className="mx-auto flex max-w-[1440px] flex-col gap-5 px-[clamp(16px,3vw,40px)] pb-12 pt-6">
      <div
        aria-label="Demo controls"
        role="region"
        className="flex flex-wrap items-center gap-3 rounded-card border border-dashed border-line-strong px-3 py-2 text-sm text-muted"
      >
        <span className="font-semibold text-ink-2">P6.6 demo, mock data</span>
        <SegmentedControl label="Report state" options={STATES} value={state} onChange={setState} />
        <SegmentedControl label="Viewer role" options={ROLES} value={viewerRole} onChange={setViewerRole} />
      </div>
      <RecordingReport
        recording={lesson.recording}
        analysis={analysis}
        transcript={hasTranscript ? lesson.transcript : null}
        labels={lesson.labels}
        roles={lesson.roles}
        viewerRole={viewerRole}
        getPlaybackUrl={getPlaybackUrl}
      />
    </main>
  );
}
