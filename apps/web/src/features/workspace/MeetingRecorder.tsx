// "Record a meeting" (founder's Sales Executive dashboard doc, 2026-11-12): the sales rep starts and stops a
// recording in the browser. Stopping hands the audio (WebM/Opus) to the upload list as a file, so it goes through the
// same direct-to-storage upload, consent and client steps as any other (golden rule 2: no audio reaches the API).
// The microphone needs a secure page (HTTPS or localhost) and the browser's permission; both are explained if missing.

import { useEffect, useRef, useState } from "react";

import { Button, Icon } from "../../design";

const MIME = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];

function clock(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0");
  return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

function fileName(started: Date, extension: string): string {
  const stamp = new Intl.DateTimeFormat("en-IN", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata",
  }).format(started).replace(/[,:]/g, (c) => (c === ":" ? "." : "")); // prettier-ignore
  return `Meeting ${stamp}.${extension}`;
}

export function MeetingRecorder({ disabled, onRecorded }: { disabled?: boolean; onRecorded: (file: File) => void }) {
  const [state, setState] = useState<"idle" | "recording" | "error">("idle");
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const started = useRef<Date>(new Date());

  useEffect(() => {
    if (state !== "recording") return;
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [state]);

  // Leaving the page stops the microphone.
  useEffect(() => () => recorder.current?.stream.getTracks().forEach((t) => t.stop()), []);

  const start = async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setState("error");
      setError("This browser cannot record here. Use Chrome, Edge or Safari on a secure (https) page.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MIME.find((m) => MediaRecorder.isTypeSupported(m));
      const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const type = (rec.mimeType || "audio/webm").split(";")[0] ?? "audio/webm";
        const blob = new Blob(chunks, { type });
        if (blob.size > 0)
          onRecorded(new File([blob], fileName(started.current, type.includes("ogg") ? "ogg" : "webm"), { type }));
        setState("idle");
      };
      recorder.current = rec;
      started.current = new Date();
      setSeconds(0);
      rec.start(10_000); // a chunk every 10 s, so a long meeting is not held in one piece
      setState("recording");
    } catch {
      setState("error");
      setError("Sabha could not use the microphone. Allow microphone access for this site and try again.");
    }
  };

  const stop = () => recorder.current?.state === "recording" && recorder.current.stop();

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-panel border border-line bg-surface px-5 py-4">
      <div className="flex min-w-0 items-center gap-3">
        <span
          aria-hidden="true"
          className={
            state === "recording"
              ? "flex h-11 w-11 animate-pulse items-center justify-center rounded-full bg-danger-tint text-danger"
              : "flex h-11 w-11 items-center justify-center rounded-full bg-primary-tint text-primary"
          }
        >
          <Icon name="mic" size={22} />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="font-semibold text-ink">
            {state === "recording" ? (
              <>
                Recording <span className="tabular-nums">{clock(seconds)}</span>
              </>
            ) : (
              "Record a meeting"
            )}
          </span>
          <span className="text-small text-muted" role={state === "error" ? "alert" : undefined}>
            {state === "error"
              ? error
              : state === "recording"
                ? "Keep this page open. Stop when the meeting ends; it then joins the files below."
                : "Start when the meeting begins. Tell everyone it is being recorded."}
          </span>
        </span>
      </div>
      {state === "recording" ? (
        <Button onClick={stop}>Stop recording</Button>
      ) : (
        <Button variant="secondary" disabled={disabled} onClick={() => void start()}>
          Start recording
        </Button>
      )}
    </div>
  );
}
