import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { advance, failLoad, installMediaMock, loadMetadata } from "../../test/media";
import { AudioPlayer, type AudioPlayerHandle } from "./AudioPlayer";
import type { PlaybackUrl } from "./types";

let media: ReturnType<typeof installMediaMock>;
beforeEach(() => {
  media = installMediaMock();
});
afterEach(() => {
  vi.useRealTimers();
  media.restore();
});

/** getUrl that hands out url-1, url-2, ... each valid for `lifetimeMs` from the moment it is issued. */
function urls(lifetimeMs = 10 * 60_000) {
  let n = 0;
  return vi.fn(async (): Promise<PlaybackUrl> => ({
    url: `https://audio.example/playback.opus?sig=${++n}`,
    expires_at: new Date(Date.now() + lifetimeMs).toISOString(),
  }));
}

const flush = () => act(async () => {});
const audioElement = (container: HTMLElement) => container.querySelector("audio") as HTMLAudioElement;

async function setup(props: Partial<Parameters<typeof AudioPlayer>[0]> = {}) {
  const getUrl = props.getUrl ?? urls();
  const ref = createRef<AudioPlayerHandle>();
  const onTimeUpdate = vi.fn();
  const view = render(<AudioPlayer ref={ref} getUrl={getUrl} onTimeUpdate={onTimeUpdate} {...props} />);
  await flush();
  const audio = audioElement(view.container);
  return { ...view, audio, getUrl, ref, onTimeUpdate };
}

describe("AudioPlayer", () => {
  it("loads the URL from getUrl and shows position and duration", async () => {
    const { audio, getUrl } = await setup({ durationMs: 52 * 60_000 + 14_000 });

    expect(getUrl).toHaveBeenCalledTimes(1);
    expect(audio.src).toBe("https://audio.example/playback.opus?sig=1");
    expect(screen.getByText("0:00").parentElement).toHaveTextContent("0:00 of 52:14");

    loadMetadata(audio, 3 * 3600);
    advance(audio, 21 * 60 + 5);
    const slider = screen.getByRole("slider", { name: "Seek" });
    expect(slider).toHaveAttribute("aria-valuetext", "21 minutes 5 seconds of 3 hours");
    expect(slider).toHaveValue("1265");
  });

  it("plays and pauses from the button with labelled controls", async () => {
    const user = userEvent.setup();
    const { audio } = await setup();
    loadMetadata(audio);

    await user.click(screen.getByRole("button", { name: "Play" }));
    expect(media.play).toHaveBeenCalled();
    expect(audio.paused).toBe(false);
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(audio.paused).toBe(true);
    for (const name of ["Back 10 seconds", "Forward 10 seconds"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("combobox", { name: "Playback speed" })).toHaveValue("1");
  });

  it("handles the keyboard shortcuts", async () => {
    const user = userEvent.setup();
    const { audio } = await setup();
    loadMetadata(audio);
    advance(audio, 60);

    await user.keyboard(" ");
    expect(audio.paused).toBe(false);
    await user.keyboard("k");
    expect(audio.paused).toBe(true);
    await user.keyboard("K");
    expect(audio.paused).toBe(false);

    await user.keyboard("j");
    expect(audio.currentTime).toBe(50);
    await user.keyboard("l");
    await user.keyboard("l");
    expect(audio.currentTime).toBe(70);
    await user.keyboard("{ArrowLeft}");
    expect(audio.currentTime).toBe(65);
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(audio.currentTime).toBe(75);

    const speed = screen.getByRole("combobox", { name: "Playback speed" });
    await user.keyboard(">");
    expect(speed).toHaveValue("1.25");
    expect(audio.playbackRate).toBe(1.25);
    await user.keyboard("<<<<");
    expect(speed).toHaveValue("0.75"); // clamps at the slowest speed
    await user.keyboard(">>>>>>>>");
    expect(audio.playbackRate).toBe(2); // and at the fastest
  });

  it("ignores shortcuts while typing, and leaves Space to a focused button", async () => {
    const user = userEvent.setup();
    const getUrl = urls();
    const { container } = render(
      <>
        <label>
          Note <input />
        </label>
        <button type="button">Other</button>
        <AudioPlayer getUrl={getUrl} />
      </>,
    );
    await flush();
    const audio = audioElement(container);
    loadMetadata(audio);
    advance(audio, 60);

    await user.click(screen.getByRole("textbox", { name: "Note" }));
    await user.keyboard("k jl<>{ArrowLeft}");
    expect(screen.getByRole("textbox", { name: "Note" })).toHaveValue("k jl<>");
    expect(audio.paused).toBe(true);
    expect(audio.currentTime).toBe(60);
    expect(audio.playbackRate).toBe(1);

    screen.getByRole("button", { name: "Other" }).focus();
    await user.keyboard(" ");
    expect(audio.paused).toBe(true);
    await user.keyboard("k");
    expect(audio.paused).toBe(false);
  });

  it("seeks and plays through the imperative handle", async () => {
    const { audio, ref, onTimeUpdate } = await setup();
    loadMetadata(audio);

    act(() => ref.current?.seek(1_265_000));
    expect(audio.currentTime).toBe(1265);
    expect(audio.paused).toBe(false);
    expect(onTimeUpdate).toHaveBeenLastCalledWith(1_265_000);

    act(() => ref.current?.seek(5_000, { play: false }));
    expect(audio.currentTime).toBe(5);
  });

  it("restores a seek made before the audio's metadata loaded", async () => {
    const { audio, ref } = await setup();

    act(() => ref.current?.seek(90_000));
    loadMetadata(audio);
    expect(audio.currentTime).toBe(90);
    expect(media.play).toHaveBeenCalled();
  });

  it("refreshes the URL before it expires and resumes at the same position", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const getUrl = urls(5 * 60_000);
    const { audio } = await setup({ getUrl, refreshMarginMs: 60_000 });
    loadMetadata(audio);
    act(() => void audio.play());
    advance(audio, 125);

    await act(() => vi.advanceTimersByTimeAsync(4 * 60_000 - 1_000));
    expect(getUrl).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(1_000));
    expect(getUrl).toHaveBeenCalledTimes(2);
    expect(audio.src).toContain("sig=2");

    // The swap reset the element; once the new source is ready it continues where it was, still playing.
    media.play.mockClear();
    advance(audio, 0); // the new source starts at 0; the player ignores it until metadata loads
    loadMetadata(audio);
    expect(audio.currentTime).toBe(125);
    expect(media.play).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
  });

  it("refreshes before playing if the refresh time has passed (a sleeping background tab)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] }); // timers never fire, as in a throttled tab
    const getUrl = urls(5 * 60_000);
    const { audio } = await setup({ getUrl });
    loadMetadata(audio);

    vi.setSystemTime(Date.now() + 10 * 60_000);
    await act(async () => screen.getByRole("button", { name: "Play" }).click());
    expect(getUrl).toHaveBeenCalledTimes(2);
    expect(audio.paused).toBe(true);
    loadMetadata(audio);
    expect(audio.paused).toBe(false);
  });

  it("on a load error (an expired URL), refreshes once and resumes; a second error there shows a message", async () => {
    const getUrl = urls();
    const { audio } = await setup({ getUrl });
    loadMetadata(audio);
    act(() => void audio.play());
    advance(audio, 600);

    failLoad(audio);
    await flush();
    expect(getUrl).toHaveBeenCalledTimes(2);
    expect(audio.src).toContain("sig=2");
    media.play.mockClear();
    loadMetadata(audio);
    expect(audio.currentTime).toBe(600);
    expect(media.play).toHaveBeenCalledTimes(1);

    failLoad(audio);
    await flush();
    expect(getUrl).toHaveBeenCalledTimes(2); // refreshed once, not in a loop
    expect(screen.getByRole("alert")).toHaveTextContent("The audio could not be loaded.");
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await flush();
    expect(getUrl).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error when getUrl fails", async () => {
    await setup({ getUrl: vi.fn(() => Promise.reject(new Error("403"))) });
    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
