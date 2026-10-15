// Audio player for a recording's playback.opus. The URL is presigned and expires, so the player asks for it
// through `getUrl()` and asks again before it expires, or once after a load error (an expired URL answers 403,
// which a media element only reports as a network or source error). Either way playback resumes where it was.

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
  type SyntheticEvent,
} from "react";

import { Button, Select, cx } from "../../design";
import { BackIcon, ForwardIcon, PauseIcon, PlayIcon } from "./icons";
import { formatClock, formatSpoken } from "./text";
import type { PlaybackUrl } from "./types";

const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2] as const;

/** Imperative controls, for the transcript and timeline to drive the player. */
export interface AudioPlayerHandle {
  /** Seeks to `ms` (original recording timeline) and starts playing unless `play` is false. */
  seek(ms: number, options?: { play?: boolean }): void;
  play(): void;
  pause(): void;
}

export interface AudioPlayerProps {
  /** Returns a fresh presigned URL. Called on mount, before the URL expires, and once after a load error. */
  getUrl: () => Promise<PlaybackUrl>;
  /** Length of the recording, shown until the audio's own metadata has loaded. */
  durationMs?: number;
  /** Called as playback moves and after every seek, in milliseconds. */
  onTimeUpdate?: (ms: number) => void;
  /** Accessible name of the player group. */
  label?: string;
  /** How long before `expires_at` to fetch a new URL (capped at half the URL's lifetime). Default one minute. */
  refreshMarginMs?: number;
  /** Listen for keyboard shortcuts on the whole page. Default true; turn off if two players share a page. */
  shortcuts?: boolean;
  /** Show the one-line shortcut hint under the controls. Default true. */
  showShortcutHint?: boolean;
  className?: string;
}

/** Same position as a failed load, within this many seconds, counts as the same failure (no second refresh). */
const SAME_FAILURE_S = 10;
const MAX_TIMEOUT_MS = 2_147_483_647;

/** Focus is in a field where keys type text (or a native control that uses arrows and space itself). */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return target.closest("input, textarea, select") !== null;
}

/** Focus is on something Space or Enter activates, so those keys belong to it, not to the player. */
function isActivatable(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return (
    target.closest(
      'button, a[href], summary, [role="button"], [role="link"], [role="checkbox"], [role="switch"], [role="tab"], [role="option"], [role="menuitem"]',
    ) !== null
  );
}

const finiteMs = (seconds: number) => (Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : null);

export const AudioPlayer = forwardRef<AudioPlayerHandle, AudioPlayerProps>(function AudioPlayer(
  {
    getUrl,
    durationMs,
    onTimeUpdate,
    label = "Audio player",
    refreshMarginMs = 60_000,
    shortcuts = true,
    showShortcutHint = true,
    className,
  },
  ref,
) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [timeMs, setTimeMs] = useState(0);
  const [mediaDurationMs, setMediaDurationMs] = useState<number | null>(null);
  const [rate, setRate] = useState(1);
  const [failed, setFailed] = useState(false);
  const [refreshAt, setRefreshAt] = useState<number | null>(null);

  // Latest props, read from callbacks without re-subscribing.
  const getUrlRef = useRef(getUrl);
  const onTimeUpdateRef = useRef(onTimeUpdate);
  const marginRef = useRef(refreshMarginMs);
  useEffect(() => {
    getUrlRef.current = getUrl;
    onTimeUpdateRef.current = onTimeUpdate;
    marginRef.current = refreshMarginMs;
  });

  const mountedRef = useRef(false);
  const inflightRef = useRef<Promise<void> | null>(null);
  const refreshAtRef = useRef(Infinity);
  /** Last known position in seconds; survives a source swap, which resets the element's currentTime to 0. */
  const positionRef = useRef(0);
  /** Whether the person wants audio playing; a source swap or load error does not change it. */
  const wantPlayRef = useRef(false);
  /** True from setting a new src until its metadata loads; the element's time and pause events are ignored. */
  const swappingRef = useRef(false);
  /** Position (s) of the last error that triggered a refresh, so a second error there gives up. */
  const errorRefreshAtRef = useRef<number | null>(null);
  const totalMsRef = useRef(0);
  const rateRef = useRef(1);

  const totalMs = mediaDurationMs ?? durationMs ?? 0;
  useEffect(() => {
    totalMsRef.current = totalMs;
  }, [totalMs]);

  const report = useCallback((seconds: number) => {
    positionRef.current = seconds;
    setTimeMs(seconds * 1000);
    onTimeUpdateRef.current?.(seconds * 1000);
  }, []);

  const applyUrl = useCallback((playback: PlaybackUrl) => {
    const audio = audioRef.current;
    if (!audio) return;
    const expiresAt = Date.parse(playback.expires_at);
    if (Number.isFinite(expiresAt)) {
      const lifetime = Math.max(0, expiresAt - Date.now());
      const at = expiresAt - Math.min(marginRef.current, lifetime / 2);
      refreshAtRef.current = at;
      setRefreshAt(at);
    } else {
      refreshAtRef.current = Infinity;
      setRefreshAt(null);
    }
    setFailed(false);
    // Resume from the exact position, not the last timeupdate (up to 250 ms stale). After an error, or while a
    // previous swap is still loading, the element's own time is not trustworthy, so keep the last known one.
    if (!swappingRef.current && audio.readyState > 0 && !audio.error) positionRef.current = audio.currentTime;
    swappingRef.current = true;
    // Loading resets playbackRate to defaultPlaybackRate, which changeRate keeps equal to the chosen speed.
    audio.defaultPlaybackRate = rateRef.current;
    audio.src = playback.url;
    if (!wantPlayRef.current) setPlaying(false);
  }, []);

  /** Fetches a URL and swaps it in; concurrent callers share one request. */
  const loadUrl = useCallback((): Promise<void> => {
    if (inflightRef.current) return inflightRef.current;
    const request = getUrlRef
      .current()
      .then(
        (playback) => {
          if (mountedRef.current) applyUrl(playback);
        },
        () => {
          if (mountedRef.current) setFailed(true);
        },
      )
      .finally(() => {
        inflightRef.current = null;
      });
    inflightRef.current = request;
    return request;
  }, [applyUrl]);

  useEffect(() => {
    mountedRef.current = true;
    void loadUrl();
    return () => {
      mountedRef.current = false;
    };
  }, [loadUrl]);

  // Refresh before expiry, whether or not the audio is playing.
  useEffect(() => {
    if (refreshAt === null) return;
    const delay = Math.min(Math.max(0, refreshAt - Date.now()), MAX_TIMEOUT_MS);
    const timer = setTimeout(() => void loadUrl(), delay);
    return () => clearTimeout(timer);
  }, [refreshAt, loadUrl]);

  const play = useCallback(() => {
    wantPlayRef.current = true;
    const audio = audioRef.current;
    if (!audio) return;
    // A background tab may have slept through the refresh timer; never start on a URL about to expire.
    if (Date.now() >= refreshAtRef.current || swappingRef.current) {
      if (Date.now() >= refreshAtRef.current) void loadUrl();
      return; // onLoadedMetadata starts playback because wantPlayRef is set
    }
    // play() rejects if a later pause or source swap interrupts it; the events keep the UI right.
    audio.play().catch(() => undefined);
  }, [loadUrl]);

  const pause = useCallback(() => {
    wantPlayRef.current = false;
    audioRef.current?.pause();
  }, []);

  const toggle = useCallback(() => (wantPlayRef.current ? pause() : play()), [pause, play]);

  const seekTo = useCallback(
    (seconds: number) => {
      const audio = audioRef.current;
      const max = totalMsRef.current > 0 ? totalMsRef.current / 1000 : Infinity;
      const target = Math.min(Math.max(0, seconds), max);
      if (audio && !swappingRef.current) audio.currentTime = target;
      report(target); // during a swap, onLoadedMetadata restores this position
    },
    [report],
  );

  const seekBy = useCallback((delta: number) => seekTo(positionRef.current + delta), [seekTo]);

  const changeRate = useCallback((next: number) => {
    rateRef.current = next;
    setRate(next);
    const audio = audioRef.current;
    if (audio) {
      audio.defaultPlaybackRate = next;
      audio.playbackRate = next;
    }
  }, []);

  const stepRate = useCallback(
    (direction: 1 | -1) => {
      const index = SPEEDS.indexOf(rateRef.current as (typeof SPEEDS)[number]);
      const next = SPEEDS[Math.min(SPEEDS.length - 1, Math.max(0, (index < 0 ? 1 : index) + direction))];
      if (next !== undefined) changeRate(next);
    },
    [changeRate],
  );

  useImperativeHandle(
    ref,
    () => ({
      seek(ms, options) {
        seekTo(ms / 1000);
        if (options?.play !== false) play();
      },
      play,
      pause,
    }),
    [seekTo, play, pause],
  );

  useEffect(() => {
    if (!shortcuts) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      let handled = true;
      switch (key) {
        case " ":
          if (isActivatable(event.target)) return;
          toggle();
          break;
        case "k":
          toggle();
          break;
        case "j":
          seekBy(-10);
          break;
        case "l":
          seekBy(10);
          break;
        case "ArrowLeft":
          seekBy(-5);
          break;
        case "ArrowRight":
          seekBy(5);
          break;
        case "<":
          stepRate(-1);
          break;
        case ">":
          stepRate(1);
          break;
        default:
          handled = false;
      }
      if (handled) event.preventDefault();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [shortcuts, toggle, seekBy, stepRate]);

  const onLoadedMetadata = (event: SyntheticEvent<HTMLAudioElement>) => {
    const audio = event.currentTarget;
    setMediaDurationMs(finiteMs(audio.duration));
    if (!swappingRef.current) return;
    swappingRef.current = false;
    audio.playbackRate = rateRef.current;
    if (positionRef.current > 0) audio.currentTime = positionRef.current;
    if (wantPlayRef.current) audio.play().catch(() => undefined);
  };

  const onError = () => {
    const position = positionRef.current;
    const previous = errorRefreshAtRef.current;
    if (previous !== null && Math.abs(position - previous) < SAME_FAILURE_S) {
      // The fresh URL failed at the same place: this is not an expiry. Stop and say so.
      swappingRef.current = false;
      wantPlayRef.current = false;
      setPlaying(false);
      setFailed(true);
      return;
    }
    errorRefreshAtRef.current = position;
    void loadUrl();
  };

  const retry = () => {
    errorRefreshAtRef.current = null;
    setFailed(false);
    void loadUrl();
  };

  const onTime = (event: SyntheticEvent<HTMLAudioElement>) => {
    if (swappingRef.current) return;
    report(event.currentTarget.currentTime);
  };

  const totalLabel = formatClock(totalMs);
  const disabled = totalMs <= 0;

  return (
    <div role="group" aria-label={label} className={cx("flex min-w-0 flex-col gap-2", className)}>
      <audio
        ref={audioRef}
        preload="metadata"
        onLoadedMetadata={onLoadedMetadata}
        onDurationChange={(e) => setMediaDurationMs(finiteMs(e.currentTarget.duration) ?? mediaDurationMs)}
        onTimeUpdate={onTime}
        onSeeked={onTime}
        onPlay={() => {
          wantPlayRef.current = true;
          setPlaying(true);
        }}
        onPause={() => {
          if (swappingRef.current) return;
          wantPlayRef.current = false;
          setPlaying(false);
        }}
        onError={onError}
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex items-center gap-1">
          <SkipButton label="Back 10 seconds" onClick={() => seekBy(-10)} disabled={disabled}>
            <BackIcon />
          </SkipButton>
          <button
            type="button"
            onClick={toggle}
            aria-label={playing ? "Pause" : "Play"}
            aria-keyshortcuts="Space K"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-ink text-surface hover:bg-ink-2"
          >
            {playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <SkipButton label="Forward 10 seconds" onClick={() => seekBy(10)} disabled={disabled}>
            <ForwardIcon />
          </SkipButton>
        </div>
        <span className="whitespace-nowrap text-sm text-muted">
          <strong className="font-semibold text-ink">{formatClock(timeMs)}</strong> of {totalLabel}
        </span>
        <input
          type="range"
          aria-label="Seek"
          aria-valuetext={`${formatSpoken(timeMs)} of ${formatSpoken(totalMs)}`}
          min={0}
          max={Math.max(1, Math.floor(totalMs / 1000))}
          step={1}
          value={Math.floor(timeMs / 1000)}
          onChange={(e) => seekTo(Number(e.currentTarget.value))}
          disabled={disabled}
          className="h-11 min-w-[160px] flex-1 cursor-pointer accent-primary disabled:cursor-not-allowed"
        />
        <Select
          label="Playback speed"
          hideLabel
          value={String(rate)}
          onChange={(e) => changeRate(Number(e.currentTarget.value))}
          className="w-24"
        >
          {SPEEDS.map((speed) => (
            <option key={speed} value={String(speed)}>
              {speed}×
            </option>
          ))}
        </Select>
      </div>
      {failed && (
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">
          The audio could not be loaded.
          <Button variant="secondary" onClick={retry}>
            Try again
          </Button>
        </div>
      )}
      {showShortcutHint && (
        <p className="m-0 text-caption text-muted">
          Keys: <Kbd>Space</Kbd> or <Kbd>K</Kbd> play or pause, <Kbd>J</Kbd> <Kbd>L</Kbd> 10 seconds, <Kbd>←</Kbd>{" "}
          <Kbd>→</Kbd> 5 seconds, <Kbd>&lt;</Kbd> <Kbd>&gt;</Kbd> speed
        </p>
      )}
    </div>
  );
});

function SkipButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="flex h-11 w-11 items-center justify-center rounded text-ink-2 hover:bg-surface-subtle disabled:cursor-not-allowed disabled:text-muted-2"
    >
      {children}
    </button>
  );
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded-sm border border-line bg-surface-subtle px-1 font-sans text-caption text-ink-2">
      {children}
    </kbd>
  );
}
