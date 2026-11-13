import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installMediaMock } from "../../test/media";
import { RecordingReport } from "./RecordingReport";
import { mockSalesCall, mockSalesReport } from "./salesMock";

let media: ReturnType<typeof installMediaMock>;
beforeEach(() => {
  media = installMediaMock();
});
afterEach(() => media.restore());

async function renderSales() {
  const call = mockSalesCall();
  render(
    <RecordingReport
      recording={call.recording}
      analysis={mockSalesReport()}
      transcript={call.transcript}
      labels={call.labels}
      roles={call.roles}
      viewerRole="manager"
      getPlaybackUrl={vi.fn(async () => ({ url: "https://audio.example/p.opus", expires_at: "2099-01-01T00:00:00Z" }))}
    />,
  );
  await act(async () => {});
}

describe("sales report", () => {
  it("sorts the rubric by points lost and marks the two biggest to fix first", async () => {
    await renderSales();
    const panel = screen.getByRole("region", { name: "Where the points were lost" });
    const rows = Array.from(panel.querySelectorAll("button[aria-expanded]"), (b) => b.textContent ?? "");
    // (5 - score) x weight: 1.0, 0.75, 0.5, 0.3, 0.2, 0.2
    expect(rows[0]).toMatch(/^Showing the differenceFix first/);
    expect(rows[1]).toMatch(/^Turning problems into valueFix first/);
    expect(rows[2]).toMatch(/^Discovering the customer's situation/);
    expect(rows[2]).not.toMatch(/Fix first/);
    expect(rows[0]).toContain("−1.0");
    expect(rows[1]).toContain("−0.75");
    expect(within(panel).getByTestId("points-lost-total")).toHaveTextContent("2.9 of 5 points lost in total");
  });

  it("shows the level, the agreed next step and the counted talk shares", async () => {
    await renderSales();
    const scale = screen.getByRole("list", { name: "Where this sits" });
    expect(within(scale).getByRole("listitem", { current: true })).toHaveTextContent("Needs work");
    // The agreed next step shows once, in the summary's "What happens next" card.
    const next = screen.getByRole("region", { name: "In short" });
    expect(within(next).getAllByText("Details by WhatsApp, then a quote")).toHaveLength(1);
    expect(within(next).getByText(/no date said/)).toBeInTheDocument();
    const talk = screen.getByRole("region", { name: "Talk and listen" });
    expect(within(talk).getByText("Rohit 52%")).toBeInTheDocument();
    expect(within(talk).getByText("Customer 48%")).toBeInTheDocument();
  });
});
