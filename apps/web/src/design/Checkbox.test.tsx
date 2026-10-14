import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Checkbox } from "./Checkbox";

describe("Checkbox", () => {
  it("toggles when its label is clicked and is described by its description", async () => {
    render(<Checkbox label="Consent is on file" description="Required before analysis." />);
    const checkbox = screen.getByRole("checkbox", { name: "Consent is on file" });

    expect(checkbox).toHaveAccessibleDescription("Required before analysis.");
    await userEvent.setup().click(screen.getByText("Consent is on file"));
    expect(checkbox).toBeChecked();
  });

  it("has a 44px row as its touch target", () => {
    render(<Checkbox label="Show to staff" />);

    expect(screen.getByText("Show to staff").closest("label")).toHaveClass("min-h-touch");
  });
});
