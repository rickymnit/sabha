import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { words } from "./format";
import { TicketPanel } from "./TicketPanel";
import type { Ticket } from "./types";

const ev = (start_ms: number, quote: string) => ({ quote, utterance_id: "u0002", start_ms, end_ms: start_ms + 4_000 });
const TICKET: Ticket = {
  category: "payment_or_billing",
  status: "follow_up_needed",
  follow_up: { text: "Confirm when the invoice will be paid.", owner_role: "accounts team" },
  summary: "A supplier came for a meeting and asked about an unpaid invoice.",
  evidence: {
    need: ev(19_000, "invoice abhi tak pay nahi hua"),
    outcome: ev(31_000, "aap Mehta sir se baat kar lijiye"),
  },
};

describe("TicketPanel", () => {
  it("shows the category, status, summary and follow-up, with quotes that play their moment", async () => {
    const onSeek = vi.fn();
    render(<TicketPanel ticket={TICKET} onSeek={onSeek} />);
    const panel = screen.getByRole("region", { name: "Front desk ticket" });
    expect(within(panel).getByText("Payment or billing")).toBeInTheDocument();
    expect(within(panel).getByText("Follow-up needed")).toBeInTheDocument();
    expect(within(panel).getByText(TICKET.summary)).toBeInTheDocument();
    expect(within(panel).getByText("Confirm when the invoice will be paid.")).toBeInTheDocument();
    expect(within(panel).getByText("Owner: accounts team")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Play from 0:31" }));
    expect(onSeek).toHaveBeenCalledWith(31_000);
  });

  it("shows a resolved ticket without a follow-up, and a status it does not know as plain words", () => {
    const { rerender } = render(
      <TicketPanel ticket={{ ...TICKET, status: "resolved", follow_up: null }} onSeek={vi.fn()} />,
    );
    expect(screen.getByText("Resolved")).toBeInTheDocument();
    expect(screen.queryByText(/Owner:/)).not.toBeInTheDocument();
    rerender(<TicketPanel ticket={{ ...TICKET, status: "handed_over" }} onSeek={vi.fn()} />);
    expect(screen.getByText("Handed over")).toBeInTheDocument();
  });

  it("turns rubric values into words", () => {
    expect(words("appointment_or_meeting")).toBe("Appointment or meeting");
    expect(words("complaint")).toBe("Complaint");
  });
});
