import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import OverviewSpike from "./OverviewSpike";

function tableRows() {
  return within(screen.getByRole("table")).getAllByRole("row").slice(1); // skip the header row
}

describe("OverviewSpike", () => {
  it("shows every recent recording by default", () => {
    render(<OverviewSpike />);

    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    expect(tableRows()).toHaveLength(7);
    expect(screen.getByText("Showing 7 of 214")).toBeInTheDocument();
  });

  it("filters the table by conversation type", async () => {
    const user = userEvent.setup();
    render(<OverviewSpike />);
    const filters = screen.getByRole("group", { name: "Filter by type" });

    await user.click(within(filters).getByRole("button", { name: "Teaching" }));

    expect(within(filters).getByRole("button", { name: "Teaching" })).toHaveAttribute("aria-pressed", "true");
    expect(within(filters).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
    expect(tableRows().map((row) => within(row).getAllByRole("cell")[0]?.textContent)).toEqual([
      "Class 8 Science: PhotosynthesisAnjali Sharma, Main campus",
      "Class 10 Maths: Quadratic equationsRohit Meena, Vaishali Nagar",
    ]);
    expect(screen.getByText("Showing 2 of 214")).toBeInTheDocument();
  });

  it("shows a dash, not a number, for recordings without a score", () => {
    render(<OverviewSpike />);
    const transcribing = tableRows().find((row) => within(row).queryByText("Transcribing"));

    expect(transcribing).toBeDefined();
    expect(within(transcribing!).getByText("—")).toBeInTheDocument();
  });
});
