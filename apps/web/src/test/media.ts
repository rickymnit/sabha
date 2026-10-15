// jsdom has no media pipeline: play() and pause() are unimplemented and currentTime never moves. This fake keeps
// per-element state, fires the events a browser would, and lets tests move time with `advance`.

import { fireEvent } from "@testing-library/react";
import { vi } from "vitest";

interface MediaState {
  currentTime: number;
  paused: boolean;
  duration: number;
  playbackRate: number;
  defaultPlaybackRate: number;
}

const DEFAULT_DURATION_S = 3 * 60 * 60;
const states = new WeakMap<HTMLMediaElement, MediaState>();

function state(el: HTMLMediaElement): MediaState {
  let s = states.get(el);
  if (!s) {
    s = { currentTime: 0, paused: true, duration: DEFAULT_DURATION_S, playbackRate: 1, defaultPlaybackRate: 1 };
    states.set(el, s);
  }
  return s;
}

const props = ["currentTime", "paused", "duration", "playbackRate", "defaultPlaybackRate"] as const;

/** Installs the fake on HTMLMediaElement.prototype; returns spies and a restore function. */
export function installMediaMock() {
  const proto = HTMLMediaElement.prototype;
  const saved = props.map((name) => [name, Object.getOwnPropertyDescriptor(proto, name)] as const);
  for (const name of props) {
    Object.defineProperty(proto, name, {
      configurable: true,
      get(this: HTMLMediaElement) {
        return state(this)[name];
      },
      set(this: HTMLMediaElement, value: never) {
        if (name === "paused") return;
        (state(this) as unknown as Record<string, unknown>)[name] = value;
      },
    });
  }
  const play = vi.spyOn(proto, "play").mockImplementation(function (this: HTMLMediaElement) {
    const s = state(this);
    if (s.paused) {
      s.paused = false;
      fireEvent(this, new Event("play"));
    }
    return Promise.resolve();
  });
  const pause = vi.spyOn(proto, "pause").mockImplementation(function (this: HTMLMediaElement) {
    const s = state(this);
    if (!s.paused) {
      s.paused = true;
      fireEvent(this, new Event("pause"));
    }
  });
  const load = vi.spyOn(proto, "load").mockImplementation(() => undefined);

  return {
    play,
    pause,
    load,
    restore() {
      play.mockRestore();
      pause.mockRestore();
      load.mockRestore();
      for (const [name, descriptor] of saved) {
        if (descriptor) Object.defineProperty(proto, name, descriptor);
        else delete (proto as unknown as Record<string, unknown>)[name];
      }
    },
  };
}

/** The browser finished reading the header of the current src. */
export function loadMetadata(audio: HTMLMediaElement, durationS = DEFAULT_DURATION_S) {
  state(audio).duration = durationS;
  fireEvent(audio, new Event("loadedmetadata"));
}

/** Playback reached `seconds`. */
export function advance(audio: HTMLMediaElement, seconds: number) {
  state(audio).currentTime = seconds;
  fireEvent(audio, new Event("timeupdate"));
}

/** The current src failed, as an expired presigned URL (HTTP 403) does. */
export function failLoad(audio: HTMLMediaElement) {
  fireEvent(audio, new Event("error"));
}
