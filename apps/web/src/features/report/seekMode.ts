// Whether a quote's time button plays the audio there, or (no audio: an uploaded meeting transcript, ADR 0009, or
// audio deleted by retention) goes to that line of the transcript. The report sets it once for all its panels.

import { createContext, useContext } from "react";

export type SeekMode = "play" | "go";

export const SeekModeContext = createContext<SeekMode>("play");

export function useSeekMode(): SeekMode {
  return useContext(SeekModeContext);
}
