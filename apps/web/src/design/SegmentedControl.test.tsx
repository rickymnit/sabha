import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { SegmentedControl } from "./SegmentedControl";

function Harness() {
  const [value, setValue] = useState<"all" | "teaching">("all");
  return (
    <SegmentedControl
      label="Filter by type"
      value={value}
      onChange={setValue}
      options={[
        { value: "all", label: "All" },
        { value: "teaching", label: "Teaching" },
      ]}
    />
  );
}

describe("SegmentedControl", () => {
  it("is a named group of aria-pressed buttons, at least 44px tall", async () => {
    render(<Harness />);
    const group = screen.getByRole("group", { name: "Filter by type" });
    const teaching = within(group).getByRole("button", { name: "Teaching" });

    expect(within(group).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    expect(teaching).toHaveAttribute("aria-pressed", "false");
    expect(teaching).toHaveClass("min-h-touch");

    await userEvent.setup().click(teaching);
    expect(teaching).toHaveAttribute("aria-pressed", "true");
    expect(within(group).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
  });
});
