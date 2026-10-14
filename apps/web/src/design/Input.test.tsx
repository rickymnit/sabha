import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Input } from "./Input";

describe("Input", () => {
  it("is labelled and accepts typing", async () => {
    render(<Input label="School name" placeholder="For example" />);
    const input = screen.getByRole("textbox", { name: "School name" });

    await userEvent.setup().type(input, "Greenfield");
    expect(input).toHaveValue("Greenfield");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).toHaveClass("min-h-touch");
  });

  it("links the hint and error and marks the field invalid", () => {
    render(<Input label="Weight" hint="Weights add up to 100%." error="Enter a number from 0 to 100." />);
    const input = screen.getByRole("textbox", { name: "Weight" });

    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Weights add up to 100%. Enter a number from 0 to 100.");
  });

  it("keeps a hidden label for screen readers when there is an icon", () => {
    render(<Input type="search" label="Search recordings" hideLabel leadingIcon={<svg />} />);

    expect(screen.getByRole("searchbox", { name: "Search recordings" })).toBeInTheDocument();
    expect(screen.getByText("Search recordings")).toHaveClass("sr-only");
  });
});
