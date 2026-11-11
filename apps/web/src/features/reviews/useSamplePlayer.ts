// Plays one stretch of a recording at a time from a presigned URL, fetching a fresh URL when there is none yet or
// it has expired. Used by the Reviews page for voice samples, evidence quotes and times named in a dispute.

import { useEffect, useRef, useState } from "react";

export interface SamplePlayer {
  /** Plays from startMs (until endMs, if given); pressing the same start again stops it. */
  play: (startMs: number, endMs?: number) => Promise<void>;
  /** The start of the stretch playing now, or null. */
  playing: number | null;
}

export function useSamplePlayer(url: string | undefined, refresh: () => Promise<string | undefined>): SamplePlayer {
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
    const onPause = () => setPlaying(null);
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("pause", onPause);
    audio.current = element;
    return () => {
      element.pause();
      element.removeEventListener("timeupdate", onTime);
      element.removeEventListener("pause", onPause);
      audio.current = null;
    };
  }, []);

  const play = async (startMs: number, endMs?: number) => {
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
    stopAt.current = endMs ?? null;
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
