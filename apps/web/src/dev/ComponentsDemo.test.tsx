import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ComponentsDemo from "./ComponentsDemo";

describe("ComponentsDemo", () => {
  it("renders every component section with a single h1", () => {
    render(<ComponentsDemo />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const name of ["Button", "StatusChip", "TypeDot", "ProgressBar", "EmptyState", "Toast", "Skeleton"]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
    expect(screen.getByRole("table", { name: "Recent recordings" })).toBeInTheDocument();
  });

  it("filters the table and raises an error toast with a request id", async () => {
    const user = userEvent.setup();
    render(<ComponentsDemo />);

    await user.click(
      within(screen.getByRole("group", { name: "Filter by type" })).getByRole("button", { name: "Sales" }),
    );
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Show error toast" }));
    expect(within(screen.getByRole("alert")).getByText("req_01J9Z4K7X2M8")).toBeInTheDocument();
  });
});
