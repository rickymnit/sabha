import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { advance, installMediaMock, loadMetadata } from "../../test/media";
import { AudioPlayer, type AudioPlayerHandle } from "./AudioPlayer";
import { generateMockTranscript } from "./mock";
import { TranscriptList } from "./TranscriptList";
import type { RoleLabels, Utterance } from "./types";

// jsdom does no layout, so every element measures 0. Give rows and the scrolling area the sizes a browser would.
const ROW_PX = 44;
const VIEWPORT_PX = 440;
let restoreLayout: () => void;
let media: ReturnType<typeof installMediaMock>;

beforeEach(() => {
  const proto = HTMLElement.prototype;
  const offsetHeight = Object.getOwnPropertyDescriptor(proto, "offsetHeight");
  const isScroller = (el: Element) => el.hasAttribute("data-transcript-scroller");
  Object.defineProperty(proto, "offsetHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return isScroller(this) ? VIEWPORT_PX : ROW_PX;
    },
  });
  Object.defineProperty(proto, "clientHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return isScroller(this) ? VIEWPORT_PX : ROW_PX;
    },
  });
  // The scroll range is the virtual list's full height.
  Object.defineProperty(proto, "scrollHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return isScroller(this) ? parseFloat((this.firstElementChild as HTMLElement | null)?.style.height ?? "0") : 0;
    },
  });
  // jsdom has no Element.scrollTo. Jump straight there and, like a browser, fire "scroll" after the call returns.
  proto.scrollTo = function (this: HTMLElement, options?: ScrollToOptions | number) {
    if (typeof options === "object" && options.top !== undefined) this.scrollTop = options.top;
    queueMicrotask(() => fireEvent.scroll(this));
  } as typeof proto.scrollTo;
  restoreLayout = () => {
    if (offsetHeight) Object.defineProperty(proto, "offsetHeight", offsetHeight);
    // These three live on Element.prototype in jsdom (or nowhere); removing the overrides uncovers them again.
    for (const name of ["clientHeight", "scrollHeight", "scrollTo"]) Reflect.deleteProperty(proto, name);
  };
  media = installMediaMock();
});
afterEach(() => {
  restoreLayout();
  media.restore();
});

// Labels as the tenant's dictionary would supply them; the test checks they are shown, not hard-coded words.
const roles: RoleLabels = { teacher: { label: "Mentor", analysed: true }, students: { label: "Class" } };

const line = (start_ms: number, role: string, text: string, extra: Partial<Utterance> = {}): Utterance => ({
  role,
  speaker_label: role === "teacher" ? "SPEAKER_00" : "SPEAKER_01",
  start_ms,
  end_ms: start_ms + 3_000,
  text,
  avg_confidence: 0.9,
  low_confidence_spans: [],
  ...extra,
});

const lesson: Utterance[] = [
  line(1_231_000, "teacher", "So the light reaction gives us ATP, NADPH and oxygen through the stomata."),
  line(1_252_000, "teacher", "This oxygen is what we breathe. Isliye plants itne important hain."),
  line(1_265_000, "teacher", "Sab samajh aaya? Okay, good, let us move to the worksheet.", {
    low_confidence_spans: [[4, 10]],
  }),
  line(1_269_000, "students", "Yes ma'am."),
  line(1_274_000, "teacher", "Take out page 44. Stomata questions first."),
  line(1_290_000, "visitor", "Excuse me, ma'am."),
];

/** Player and transcript wired together as the recording page does it. */
function Harness({ utterances = lesson }: { utterances?: Utterance[] }) {
  const player = useRef<AudioPlayerHandle>(null);
  const [currentMs, setCurrentMs] = useState<number | null>(null);
  return (
    <>
      <AudioPlayer
        ref={player}
        getUrl={async () => ({ url: "https://audio.example/a.opus", expires_at: "2099-01-01T00:00:00Z" })}
        onTimeUpdate={setCurrentMs}
        showShortcutHint={false}
      />
      <TranscriptList
        utterances={utterances}
        roles={roles}
        currentMs={currentMs}
        onSeek={(ms) => player.current?.seek(ms)}
      />
    </>
  );
}

async function setup(utterances?: Utterance[]) {
  const view = render(<Harness utterances={utterances} />);
  await act(async () => {});
  const audio = view.container.querySelector("audio") as HTMLAudioElement;
  loadMetadata(audio);
  return { ...view, audio };
}

/** The transcript line whose text contains `text` (text may be split by highlights, so match on textContent). */
const row = (text: string) => {
  const found = screen.getAllByRole("button").find((b) => b.hasAttribute("data-line") && b.textContent?.includes(text));
  if (!found) throw new Error(`no transcript line contains ${JSON.stringify(text)}`);
  return found;
};

describe("TranscriptList", () => {
  it("shows time, role label from props and text for each line", async () => {
    await setup();
    const list = screen.getByRole("list", { name: "Transcript lines" });
    const first = within(list).getAllByRole("listitem")[0] as HTMLElement;
    expect(first).toHaveTextContent("20:31");
    expect(first).toHaveTextContent("Mentor");
    expect(within(list).getAllByText("Class")).toHaveLength(1);
    // A role the labels do not cover falls back to the anonymous speaker label.
    expect(row("Excuse me")).toHaveTextContent("SPEAKER_01");
  });

  it("seeks the audio to a line's start when the line is clicked, and plays", async () => {
    const user = userEvent.setup();
    const { audio } = await setup();

    await user.click(row("Yes ma'am."));
    expect(audio.currentTime).toBe(1_269);
    expect(audio.paused).toBe(false);
    expect(row("Yes ma'am.")).toHaveAttribute("aria-current", "true");
  });

  it("seeks with Enter or Space on a focused line, and moves between lines with the arrow keys", async () => {
    const user = userEvent.setup();
    const { audio } = await setup();

    row("So the light reaction").focus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(row("Sab samajh aaya?")).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(audio.currentTime).toBe(1_265);

    await user.keyboard("{ArrowDown}");
    expect(row("Yes ma'am.")).toHaveFocus();
    await user.keyboard(" ");
    expect(audio.currentTime).toBe(1_269);
    expect(audio.paused).toBe(false); // Space seeked and kept playing; the player's shortcut did not pause it
  });

  it("highlights the line being played as time moves", async () => {
    const { audio } = await setup();
    const current = () => screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "true");

    expect(current()).toHaveLength(0);
    advance(audio, 1_252.4);
    expect(current()).toEqual([row("This oxygen")]);
    advance(audio, 1_270);
    expect(current()).toEqual([row("Yes ma'am.")]);
    advance(audio, 1_272); // the pause after a line keeps it highlighted
    expect(current()).toEqual([row("Yes ma'am.")]);
    advance(audio, 1_275);
    expect(current()).toEqual([row("Take out page 44")]);
  });

  it("marks low-confidence words with a dotted underline and a title, not colour alone", async () => {
    await setup();
    const uncertain = screen.getByTitle("The speech recogniser was unsure of these words");
    expect(uncertain).toHaveTextContent(/^samajh$/);
    expect(uncertain).toHaveClass("decoration-dotted", "underline");
  });

  it("searches with a match count, next and previous, and highlights the hits", async () => {
    const user = userEvent.setup();
    await setup();
    const search = screen.getByRole("searchbox", { name: "Search the transcript" });

    await user.type(search, "stomata");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    const marks = () => document.querySelectorAll("mark");
    expect(marks()).toHaveLength(2);
    const active = () => document.querySelector("mark[data-active-match]")?.closest('[role="button"]');
    expect(active()).toBe(row("So the light reaction"));

    await user.click(screen.getByRole("button", { name: "Next match" }));
    expect(screen.getByText("2 of 2")).toBeInTheDocument();
    expect(active()).toBe(row("Take out page 44"));
    await user.click(screen.getByRole("button", { name: "Next match" }));
    expect(screen.getByText("1 of 2")).toBeInTheDocument(); // wraps
    await user.click(screen.getByRole("button", { name: "Previous match" }));
    expect(screen.getByText("2 of 2")).toBeInTheDocument();

    await user.keyboard("{Shift>}{Enter}{/Shift}");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(screen.getByText("2 of 2")).toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "photosynthesis");
    expect(screen.getByText("No matches")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next match" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(search).toHaveValue("");
    expect(marks()).toHaveLength(0);
  });

  it("does not seek when typing a search term containing shortcut keys", async () => {
    const user = userEvent.setup();
    const { audio } = await setup();
    advance(audio, 100);
    await user.type(screen.getByRole("searchbox"), "jkl ");
    expect(audio.currentTime).toBe(100);
    expect(audio.paused).toBe(true);
  });

  it("renders 5,000 lines while mounting only a small window, and follows playback deep into the list", async () => {
    const utterances = generateMockTranscript({ lines: 5_000 }).utterances;
    const started = performance.now();
    const { audio } = await setup(utterances);
    const elapsed = performance.now() - started;

    const list = screen.getByRole("list");
    const mounted = () => within(list).getAllByRole("listitem");
    expect(mounted().length).toBeGreaterThan(5);
    expect(mounted().length).toBeLessThanOrEqual(VIEWPORT_PX / ROW_PX + 2 * 6 + 2); // view + overscan + tab stop
    expect(mounted()[0]).toHaveAttribute("aria-setsize", "5000");
    expect(list).toHaveStyle({ height: `${5_000 * ROW_PX}px` });
    expect(elapsed).toBeLessThan(5_000); // generous: only guards against rendering all 5,000 rows

    // Scrolling mounts the lines in view and unmounts the rest.
    const scroller = document.querySelector("[data-transcript-scroller]") as HTMLElement;
    act(() => {
      scroller.scrollTop = 2_500 * ROW_PX;
      fireEvent.scroll(scroller);
    });
    const positions = mounted().map((item) => Number(item.getAttribute("aria-posinset")));
    expect(positions).toContain(2_501);
    // Everything mounted is near the scroll position, apart from line 1: the list's single tab stop stays mounted.
    expect(positions.filter((p) => p !== 1).every((p) => Math.abs(p - 2_501) <= 20)).toBe(true);
    expect(mounted().length).toBeLessThanOrEqual(VIEWPORT_PX / ROW_PX + 2 * 6 + 2);

    // Playback far down the list mounts and highlights that line.
    const target = utterances[4_200] as Utterance;
    loadMetadata(audio, (utterances[4_999] as Utterance).end_ms / 1000); // 5,000 mock lines run about 7 hours
    await act(async () => advance(audio, target.start_ms / 1000 + 0.1));
    const highlighted = list.querySelector('[aria-current="true"]');
    expect(highlighted).toHaveAttribute("data-line", "4200");
    // ...and scrolled it into the middle of the view.
    expect(scroller.scrollTop).toBe(4_200 * ROW_PX - VIEWPORT_PX / 2 + ROW_PX / 2);
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((i) => i.getAttribute("aria-posinset")),
    ).toContain("4202");
    expect(mounted().length).toBeLessThanOrEqual(VIEWPORT_PX / ROW_PX + 2 * 6 + 2);

    // Clicking it seeks to exactly its start.
    fireEvent.click(highlighted as HTMLElement);
    expect(audio.currentTime).toBe(target.start_ms / 1000);
  });

  it("keeps one line in the tab order", async () => {
    await setup();
    const tabbable = screen.getAllByRole("button").filter((b) => b.closest('[role="list"]') && b.tabIndex === 0);
    expect(tabbable).toHaveLength(1);
  });
});

// Guard against a test leaving fake timers on.
afterEach(() => vi.useRealTimers());
