import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Tabs } from "./Tabs";

const tabs = [
  { value: "summary", label: "Summary", panel: "Summary body" },
  { value: "transcript", label: "Transcript", panel: "Transcript body" },
  { value: "evidence", label: "Evidence", panel: "Evidence body" },
];

describe("Tabs", () => {
  it("links tabs to panels and selects on click", async () => {
    const onChange = vi.fn();
    render(<Tabs label="Report sections" tabs={tabs} onChange={onChange} />);

    expect(screen.getByRole("tablist", { name: "Report sections" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Summary" })).toHaveTextContent("Summary body");

    await userEvent.setup().click(screen.getByRole("tab", { name: "Evidence" }));
    expect(onChange).toHaveBeenCalledWith("evidence");
    expect(screen.getByRole("tabpanel", { name: "Evidence" })).toHaveTextContent("Evidence body");
  });

  it("moves with arrow keys, Home and End, using a roving tabindex", async () => {
    const user = userEvent.setup();
    render(<Tabs label="Report sections" tabs={tabs} />);

    await user.tab();
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("tabindex", "-1");

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Transcript" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Evidence" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Evidence" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
  });

  it("follows a controlled value", () => {
    render(<Tabs label="Report sections" tabs={tabs} value="transcript" />);

    expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  });
});
