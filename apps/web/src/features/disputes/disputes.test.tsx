import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DisputeDecision } from "../reviews/DisputeDecision";
import { mockReviewItems } from "../reviews/mock";
import { DisputeDialog } from "./DisputeDialog";

const DIMENSIONS = [
  { key: "checks_for_understanding", name: "Checks for understanding", score: 2 },
  { key: "pacing", name: "Pacing", score: 4 },
];

function openDialog(onSubmit = vi.fn(async () => {}), onClose = vi.fn()) {
  render(
    <DisputeDialog
      open
      dimensions={DIMENSIONS}
      initialKey="checks_for_understanding"
      onSubmit={onSubmit}
      onClose={onClose}
    />,
  );
  return { onSubmit, onClose, user: userEvent.setup() };
}

describe("DisputeDialog", () => {
  it("is a labelled modal that takes focus", () => {
    openDialog();
    const dialog = screen.getByRole("dialog", { name: "Dispute a score" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("sends the dimension, the proposed score and the reason", async () => {
    const { onSubmit, onClose, user } = openDialog();
    await user.click(screen.getByRole("radio", { name: "3" }));
    await user.type(screen.getByRole("textbox", { name: "Why" }), "I asked three students to explain it back.");
    await user.click(screen.getByRole("button", { name: "Send dispute" }));
    expect(onSubmit).toHaveBeenCalledWith({
      dimension_key: "checks_for_understanding",
      proposed_score: 3,
      comment: "I asked three students to explain it back.",
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("does not offer the current score", () => {
    openDialog();
    expect(screen.getByRole("radio", { name: "2" })).toBeDisabled();
  });

  it("needs a reason before sending", async () => {
    const { onSubmit, user } = openDialog();
    await user.click(screen.getByRole("radio", { name: "3" }));
    await user.type(screen.getByRole("textbox", { name: "Why" }), "too short");
    await user.click(screen.getByRole("button", { name: "Send dispute" }));
    expect(screen.getByRole("alert")).toHaveTextContent("at least 10 characters");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    const { onClose, user } = openDialog();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps the dialog open and says so when sending fails", async () => {
    const { onClose, user } = openDialog(vi.fn(async () => Promise.reject(new Error("network"))));
    await user.click(screen.getByRole("radio", { name: "4" }));
    await user.type(screen.getByRole("textbox", { name: "Why" }), "The pacing was planned on purpose.");
    await user.click(screen.getByRole("button", { name: "Send dispute" }));
    expect(screen.getByRole("alert")).toHaveTextContent("could not be sent");
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("DisputeDecision", () => {
  const dispute = () => {
    const item = mockReviewItems()[0];
    if (item?.kind !== "dispute") throw new Error("the first mock item is a dispute");
    return item;
  };
  function setup(change: Partial<ReturnType<typeof dispute>> = {}) {
    const onResolve = vi.fn(async () => {});
    const player = { play: vi.fn(async () => {}), playing: null };
    render(
      <DisputeDecision
        item={{ ...dispute(), ...change }}
        player={player}
        recordingHref="/recordings/rec_101"
        onResolve={onResolve}
      />,
    );
    return { onResolve, player, user: userEvent.setup() };
  }

  it("accepts the proposed score without a note", async () => {
    const { onResolve, user } = setup();
    await user.click(screen.getByRole("button", { name: "Accept 3" }));
    expect(onResolve).toHaveBeenCalledWith({ decision: "accepted", final_score: 3 });
  });

  it("keeping the AI score needs a note, which is sent", async () => {
    const { onResolve, user } = setup();
    const keep = screen.getByRole("button", { name: "Keep AI score 2" });
    expect(keep).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Note to Anjali" }), "The checks were yes or no only.");
    await user.click(keep);
    expect(onResolve).toHaveBeenCalledWith({ decision: "rejected", note: "The checks were yes or no only." });
  });

  it("sets a score nobody proposed, with a note", async () => {
    const { onResolve, user } = setup();
    await user.type(screen.getByRole("textbox", { name: "Note to Anjali" }), "One real check, at 12 minutes.");
    await user.click(screen.getByRole("button", { name: "Set a different score" }));
    const scores = within(screen.getByRole("group", { name: "Final score" }));
    expect(scores.queryByRole("radio", { name: "2" })).toBeNull(); // the score shown now
    expect(scores.queryByRole("radio", { name: "3" })).toBeNull(); // that is "Accept 3"
    await user.click(scores.getByRole("radio", { name: "4" }));
    await user.click(screen.getByRole("button", { name: "Set score 4" }));
    expect(onResolve).toHaveBeenCalledWith({
      decision: "accepted",
      final_score: 4,
      note: "One real check, at 12 minutes.",
    });
  });

  it("plays the moment the reason names", async () => {
    const { player, user } = setup({ comment: "I did a thumbs-up check at 22:30 that the transcript missed." });
    await user.click(screen.getByRole("button", { name: "Play the moment named at 22:30" }));
    expect(player.play).toHaveBeenCalledWith(1_350_000, 1_365_000);
  });

  it("says someone else decides a dispute you raised", () => {
    setup({ raised_by_me: true });
    expect(screen.getByText(/You raised this dispute, so another reviewer/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept 3" })).toBeNull();
  });
});
