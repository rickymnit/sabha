import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installMediaMock } from "../test/media";
import TranscriptDemo from "./TranscriptDemo";

// Building a 3-hour WAV is slow and pointless in jsdom; the demo only needs a Blob.
vi.mock("./synthAudio", () => ({ synthesizeWav: () => new Blob(["RIFF"], { type: "audio/wav" }) }));

let media: ReturnType<typeof installMediaMock>;
beforeEach(() => {
  media = installMediaMock();
  let n = 0;
  URL.createObjectURL = vi.fn(() => `blob:demo/${++n}`);
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => media.restore());

describe("TranscriptDemo", () => {
  it("shows the player and transcript for the 3-hour mock, and switches to the short clip", async () => {
    const user = userEvent.setup();
    render(<TranscriptDemo />);

    expect(screen.getByRole("heading", { level: 1, name: "Transcript and player" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(await screen.findByText(/Playback URL issued 1 time;/)).toBeInTheDocument();
    expect(screen.getByText(/3:00:\d\d of synthesised audio/)).toBeInTheDocument();
    expect(screen.getByText(/\d,\d{3} lines/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Transcript lines" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "2-minute clip" }));
    expect(await screen.findByText(/Playback URL issued 1 time;/)).toBeInTheDocument();
    expect(screen.getByText(/2:\d\d of synthesised audio/)).toBeInTheDocument();
  });
});
