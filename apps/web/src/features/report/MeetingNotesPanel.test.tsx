import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { meetingView, voiceLabel } from "../../pages/recordingView";
import { MeetingNotesPanel } from "./MeetingNotesPanel";
import type { MeetingNotes } from "./types";

const ev = (start_ms: number, quote: string) => ({ quote, utterance_id: "u0001", start_ms, end_ms: start_ms + 4_000 });
const NOTES: MeetingNotes = {
  decisions: [{ decision: "The campaign budget is Rs 2 lakh.", evidence: ev(20_500, "budget do lakh") }],
  action_items: [
    { action: "Call the vendor.", owner: null, owner_voice: "S2", due: "tomorrow 12", evidence: ev(26_500, "kal call kar dungi") },
    { action: "Draft the hiring post.", owner: "Aman", owner_voice: null, due: null, evidence: ev(40_000, "Aman post likh dega") },
  ],
  open_questions: [{ question: "When is the new hire needed?", evidence: ev(34_500, "naya hire kab tak") }],
  left_out: 0,
}; // prettier-ignore

describe("MeetingNotesPanel", () => {
  it("shows actions with who and when, decisions and open questions, each playable", async () => {
    const onSeek = vi.fn();
    render(<MeetingNotesPanel notes={NOTES} voiceName={(v) => (v === "S2" ? "Riya" : v)} onSeek={onSeek} />);
    const notes = screen.getByRole("region", { name: "Meeting notes" });
    expect(within(notes).getByText("Riya")).toBeInTheDocument(); // the voice, by the name people gave it
    expect(within(notes).getByText("Aman")).toBeInTheDocument(); // as named in the meeting
    expect(within(notes).getByText("No date said")).toBeInTheDocument();
    expect(within(notes).getByText("The campaign budget is Rs 2 lakh.")).toBeInTheDocument();
    expect(within(notes).getByText("When is the new hire needed?")).toBeInTheDocument();
    await userEvent.click(within(notes).getByRole("button", { name: "Play from 0:26" }));
    expect(onSeek).toHaveBeenCalledWith(26_500);
  });
});

describe("meetingView", () => {
  it("shows each voice by its name, or Voice n in order of first speech", () => {
    const u = (speaker_label: string, start_ms: number) => ({
      role: "participant", speaker_label, start_ms, end_ms: start_ms + 1_000, text: "haan",
      avg_confidence: null, low_confidence_spans: [],
    }); // prettier-ignore
    const transcript = { utterances: [u("S1", 0), u("S0", 2_000), u("S1", 4_000)] } as never;
    const view = meetingView(transcript, { S0: "Riya" });
    expect(view.voices).toEqual(["S1", "S0"]);
    expect(view.roles).toEqual({ S1: { label: "Voice 1" }, S0: { label: "Riya" } });
    expect(view.transcript.utterances.map((x) => x.role)).toEqual(["S1", "S0", "S1"]);
    expect(voiceLabel("S1", view.voices, {})).toBe("Voice 1");
  });
});
