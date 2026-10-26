import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DealCardPanel } from "./DealCardPanel";
import type { DealCard, Labels } from "./types";

const labels: Labels = { person: "Sales rep", person_plural: "Team", recording: "Conversation",
                         recording_plural: "Conversations", unit: "Team", manager: "Sales head" }; // prettier-ignore
const ev = (start_ms: number, quote: string) => ({ quote, utterance_id: "u0001", start_ms, end_ms: start_ms + 4_000 });
const CARD: DealCard = {
  current_setup: [{ fact: "Uses another ERP at Rs 12 per student a month.", evidence: ev(60_000, "abhi toh 10 12 rupaye") }],
  customer_needs: [{ need: "Cut the two days spent on reconciliation.", evidence: ev(27_000, "do din lag jaate hain") }],
  objections: [
    { objection: "Price is above this quarter's budget.", response: "Quarterly billing from April.", settled: "yes",
      evidence: ev(109_000, "budget ke hisaab se thoda zyada") },
    { objection: "Worried about moving five years of data.", response: "Our team will do it.", settled: "unclear",
      evidence: ev(127_000, "purana data Excel mein hai") },
  ],
  interest_level: { value: "medium", evidence: ev(94_000, "lekin price kya hoga") },
  next_step: { action: "Send the quotation and hold a call.", owner: "both", due: "Thursday 4 pm",
               evidence: ev(154_000, "Thursday chaar baje theek") },
  left_out: 1,
}; // prettier-ignore

describe("DealCardPanel", () => {
  it("shows the next step, needs, objections and interest, each with a quote that plays its moment", async () => {
    const onSeek = vi.fn();
    render(<DealCardPanel card={CARD} labels={labels} onSeek={onSeek} />);
    const card = screen.getByRole("region", { name: "Deal card" });
    expect(within(card).getByText("Some interest")).toBeInTheDocument();
    expect(within(card).getByText("Send the quotation and hold a call.")).toBeInTheDocument();
    expect(within(card).getByText("Both sides, Thursday 4 pm")).toBeInTheDocument();
    expect(within(card).getByText("Cut the two days spent on reconciliation.")).toBeInTheDocument();
    expect(within(card).getByText("Uses another ERP at Rs 12 per student a month.")).toBeInTheDocument();
    expect(within(card).getByText("Settled")).toBeInTheDocument();
    expect(within(card).getByText("Unclear")).toBeInTheDocument();
    expect(within(card).getByText(/1 item was left out because its words could not be found/)).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Play from 2:34" }));
    expect(onSeek).toHaveBeenCalledWith(154_000);
  });

  it("says plainly when nothing was agreed and no objection was raised", () => {
    render(
      <DealCardPanel
        card={{ ...CARD, next_step: null, objections: [], current_setup: [], left_out: 0 }}
        labels={labels}
        onSeek={vi.fn()}
      />,
    );
    expect(screen.getByText("No next step was agreed in this meeting.")).toBeInTheDocument();
    expect(screen.getByText("The customer raised no objections.")).toBeInTheDocument();
    expect(screen.queryByText(/left out/)).toBeNull();
    expect(screen.queryByText("What they use today")).toBeNull(); // nothing said about it: no empty section
  });
});
