import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReviewsPage } from "../reviews/ReviewsPage";
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

describe("ReviewsPage", () => {
  function setup() {
    const onResolve = vi.fn(async () => {});
    render(<ReviewsPage items={mockReviewItems()} onResolve={onResolve} recordingHref={(id) => `/recordings/${id}`} />);
    return { onResolve, user: userEvent.setup() };
  }
  const queue = () => within(screen.getByRole("list", { name: /Queue/ })).getAllByRole("button");

  it("shows open items by default and can show everything", async () => {
    const { user } = setup();
    expect(queue()).toHaveLength(2); // the rejected dispute is hidden
    await user.click(within(screen.getByRole("group", { name: "Status" })).getByRole("button", { name: "All" }));
    expect(queue()).toHaveLength(3);
  });

  it("filters to disputes only", async () => {
    const { user } = setup();
    await user.click(within(screen.getByRole("group", { name: "Show" })).getByRole("button", { name: "Disputes" }));
    expect(queue()).toHaveLength(1);
  });

  it("accepting needs a note and sends the final score", async () => {
    const { onResolve, user } = setup();
    await user.click(screen.getByRole("button", { name: "Accept and set score" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Add a note");
    expect(onResolve).not.toHaveBeenCalled();

    await user.type(screen.getByRole("textbox", { name: "Note to the person" }), "Agreed: two real checks at 12 min.");
    await user.click(screen.getByRole("button", { name: "Accept and set score" }));
    expect(onResolve).toHaveBeenCalledWith("dsp_001", {
      decision: "accepted",
      final_score: 3,
      note: "Agreed: two real checks at 12 min.",
    });
  });

  it("rejecting sends no score", async () => {
    const { onResolve, user } = setup();
    await user.type(screen.getByRole("textbox", { name: "Note to the person" }), "The checks were yes/no only.");
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(onResolve).toHaveBeenCalledWith("dsp_001", { decision: "rejected", note: "The checks were yes/no only." });
  });

  it("links a needs-review item to its recording", async () => {
    const { user } = setup();
    await user.click(queue()[1]!);
    await act(async () => {});
    expect(screen.getByRole("link", { name: "Open the recording" })).toHaveAttribute("href", "/recordings/rec_102");
    expect(screen.queryByRole("button", { name: "Accept and set score" })).toBeNull();
  });
});
