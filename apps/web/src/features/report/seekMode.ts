// Whether a quote's time button plays the audio there, or (no audio: an uploaded meeting transcript, ADR 0009, or
// audio deleted by retention) goes to that line of the transcript. The report sets it once for all its panels.

import { createContext, useContext } from "react";

export type SeekMode = "play" | "go";

export const SeekModeContext = createContext<SeekMode>("play");

export function useSeekMode(): SeekMode {
  return useContext(SeekModeContext);
}

/**
 * The time (ms) the audio is playing from after a time button was pressed, or null when paused. A time button
 * whose time matches shows a pause icon: pressing it again pauses, and once more carries on from there.
 */
export const PlayingFromContext = createContext<number | null>(null);

export function usePlayingFrom(): number | null {
  return useContext(PlayingFromContext);
}
