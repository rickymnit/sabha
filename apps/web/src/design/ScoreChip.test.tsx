import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreChip } from "./ScoreChip";

describe("ScoreChip", () => {
  it.each([
    [2.9, "low", ["bg-danger-tint", "text-danger"]],
    [3, "mid", ["bg-warning-tint", "text-warning"]],
    [3.7, "mid", ["bg-warning-tint", "text-warning"]],
    [3.8, "good", ["bg-success-tint", "text-success"]],
  ] as const)("colours %s as %s", (score, band, classes) => {
    const { container } = render(<ScoreChip score={score} decimals={2} />);

    const chip = container.firstElementChild;
    expect(chip).toHaveAttribute("data-band", band);
    expect(chip).toHaveClass(...classes, "tabular-nums");
  });

  it("formats whole numbers without decimals unless asked, and says out of 5", () => {
    const { rerender } = render(<ScoreChip score={4} />);
    expect(screen.getByText("4", { exact: false })).toHaveTextContent("4 out of 5");

    rerender(<ScoreChip score={3} variant="text" decimals={1} />);
    expect(screen.getByText("3.0", { exact: false })).toHaveClass("text-warning");
    expect(screen.getByText("3.0", { exact: false })).not.toHaveClass("bg-warning-tint");
  });

  it("shows a dash with screen-reader text when there is no score", () => {
    render(<ScoreChip score={null} emptyLabel="Not scored yet" />);

    expect(screen.getByText("—")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("Not scored yet")).toHaveClass("sr-only");
  });
});
