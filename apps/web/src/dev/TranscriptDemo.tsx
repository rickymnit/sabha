// Demo of the transcript view (P6.5), served at /dev/transcript in development only (see main.tsx).
// Mock transcript and audio synthesised in the browser; the real page reads GET /v1/recordings/{id}/transcript.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader, Panel, SegmentedControl } from "../design";
import {
  AudioPlayer,
  TranscriptList,
  formatClock,
  type AudioPlayerHandle,
  type PlaybackUrl,
  type RoleLabels,
} from "../features/transcript";
import { generateMockTranscript } from "../features/transcript/mock";
import { synthesizeWav } from "./synthAudio";

// Stand-in for the tenant's labels dictionary (P1.7). It has no word for the people who are not analysed yet,
// so `group` is a placeholder for whatever key that decision adds.
const labels = { person: "Teacher", recording: "Lesson", group: "Students" };
const roles: RoleLabels = {
  teacher: { label: labels.person, analysed: true },
  students: { label: labels.group },
};

type Length = "long" | "short";
const lengths = {
  long: { label: "3-hour recording", durationMs: 3 * 60 * 60 * 1000, sampleRate: 3000, seed: 1 },
  short: { label: "2-minute clip", durationMs: 2 * 60 * 1000, sampleRate: 16000, seed: 7 },
} as const;

/** Each URL "expires" after this long so the refresh can be watched; the player refreshes 15 s early. */
const URL_LIFETIME_MS = 45_000;
const REFRESH_MARGIN_MS = 15_000;

const clockIst = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", timeStyle: "medium" });

export default function TranscriptDemo() {
  const [length, setLength] = useState<Length>("long");
  const config = lengths[length];
  const transcript = useMemo(
    () => generateMockTranscript({ durationMs: config.durationMs, seed: config.seed }),
    [config],
  );
  const utterances = transcript.utterances;
  const durationMs = (utterances[utterances.length - 1]?.end_ms ?? 0) + 2_000;

  const [audio, setAudio] = useState<{ length: Length; blob: Blob } | null>(null);
  useEffect(() => {
    // Yield first so the "preparing" message paints; a 3-hour file takes a moment to build.
    const timer = setTimeout(() => {
      setAudio({ length, blob: synthesizeWav(utterances, { durationMs, sampleRate: config.sampleRate }) });
    }, 0);
    return () => clearTimeout(timer);
  }, [length, utterances, durationMs, config]);
  const blob = audio?.length === length ? audio.blob : null;

  const [issued, setIssued] = useState<{ count: number; expiresAt: number } | null>(null);
  const urlsRef = useRef<string[]>([]);
  useEffect(
    () => () => {
      urlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      urlsRef.current = [];
    },
    [blob],
  );

  // Stands in for the transcript endpoint: a new "presigned" URL each call, valid for URL_LIFETIME_MS.
  const getUrl = useCallback(async (): Promise<PlaybackUrl> => {
    if (!blob) throw new Error("audio not ready");
    const url = URL.createObjectURL(blob);
    urlsRef.current.push(url);
    // Keep the previous URL a little longer so the element can finish switching.
    while (urlsRef.current.length > 2) URL.revokeObjectURL(urlsRef.current.shift() as string);
    const expiresAt = Date.now() + URL_LIFETIME_MS;
    setIssued((prev) => ({ count: (prev?.count ?? 0) + 1, expiresAt }));
    return { url, expires_at: new Date(expiresAt).toISOString() };
  }, [blob]);

  const playerRef = useRef<AudioPlayerHandle>(null);
  const [currentMs, setCurrentMs] = useState<number | null>(null);

  return (
    <main className="mx-auto flex max-w-[1200px] flex-col gap-5 px-[clamp(16px,3vw,40px)] pb-12 pt-6">
      <PageHeader
        title="Transcript and player"
        description={`P6.5 demo with mock data: ${utterances.length.toLocaleString("en-IN")} lines, ${formatClock(durationMs)} of synthesised audio.`}
        actions={
          <SegmentedControl
            label="Demo length"
            options={(Object.keys(lengths) as Length[]).map((value) => ({ value, label: lengths[value].label }))}
            value={length}
            onChange={(value) => {
              setLength(value);
              setCurrentMs(null);
              setIssued(null);
            }}
          />
        }
      />

      <Panel title={`${labels.recording} audio`}>
        {blob ? (
          <AudioPlayer
            key={length}
            ref={playerRef}
            label={`${labels.recording} audio player`}
            getUrl={getUrl}
            durationMs={durationMs}
            onTimeUpdate={setCurrentMs}
            refreshMarginMs={REFRESH_MARGIN_MS}
          />
        ) : (
          <p className="m-0 text-sm text-muted">Preparing the audio…</p>
        )}
        {issued && (
          <p className="m-0 text-caption text-muted" data-testid="url-status">
            Playback URL issued {issued.count} {issued.count === 1 ? "time" : "times"}; the current one expires at{" "}
            {clockIst.format(issued.expiresAt)} IST and is replaced {REFRESH_MARGIN_MS / 1000} seconds before.
          </p>
        )}
      </Panel>

      <Panel title="Transcript" flush>
        <TranscriptList
          utterances={utterances}
          roles={roles}
          currentMs={currentMs}
          onSeek={(ms) => playerRef.current?.seek(ms)}
        />
      </Panel>
    </main>
  );
}
