import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgressBar } from "./ProgressBar";

describe("ProgressBar", () => {
  it("exposes its label and values", () => {
    render(<ProgressBar label="Uploading file.mp3" value={62} />);

    const bar = screen.getByRole("progressbar", { name: "Uploading file.mp3" });
    expect(bar).toHaveAttribute("aria-valuenow", "62");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuetext", "62%");
    expect(bar.firstElementChild).toHaveStyle({ width: "62%" });
  });

  it("clamps the value, uses a visible label when asked, and animates only with motion allowed", () => {
    render(<ProgressBar label="Plan hours" value={140} max={100} showLabel valueText="140 of 100" tone="danger" />);

    const bar = screen.getByRole("progressbar", { name: "Plan hours" });
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("140 of 100")).toBeVisible();
    expect(bar.firstElementChild).toHaveClass("bg-danger-bar", "motion-safe:transition-[width]");
    expect(bar.firstElementChild?.className).not.toMatch(/(^|\s)transition/);
  });
});
