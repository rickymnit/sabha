import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("is a type=button <button> by default and calls onClick", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Export PDF</Button>);
    const button = screen.getByRole("button", { name: "Export PDF" });

    expect(button).toHaveAttribute("type", "button");
    await userEvent.setup().click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("keeps an explicit type and the 44px minimum height on every variant", () => {
    render(
      <>
        <Button type="submit">Save</Button>
        <Button variant="secondary">Cancel</Button>
        <Button variant="ghost">21:05</Button>
      </>,
    );

    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "submit");
    for (const button of screen.getAllByRole("button")) expect(button).toHaveClass("min-h-touch");
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("bg-primary");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass("border-line-input");
    expect(screen.getByRole("button", { name: "21:05" })).toHaveClass("text-primary");
  });

  it("does not fire when disabled and hides the icon from assistive technology", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick} icon={<svg data-testid="icon" />}>
        Analyse
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Analyse" });

    await userEvent.setup().click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(button).toBeDisabled();
    expect(screen.getByTestId("icon").parentElement).toHaveAttribute("aria-hidden", "true");
  });
});
