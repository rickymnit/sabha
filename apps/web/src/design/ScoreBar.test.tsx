import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreBar } from "./ScoreBar";

describe("ScoreBar", () => {
  it("fills segments up to the score in the band colour", () => {
    const { container } = render(<ScoreBar score={2} />);

    const segments = container.querySelectorAll("[data-filled]");
    expect(segments).toHaveLength(5);
    expect(container.querySelectorAll("[data-filled=true]")).toHaveLength(2);
    expect(segments[0]).toHaveClass("bg-danger-bar");
    expect(segments[4]).toHaveClass("bg-line-subtle");
    expect(screen.getByText("2 of 5")).toBeInTheDocument();
  });

  it("uses the mid and good bar colours", () => {
    const { container, rerender } = render(<ScoreBar score={3} />);
    expect(container.querySelector("[data-filled=true]")).toHaveClass("bg-type-reception");

    rerender(<ScoreBar score={4} />);
    expect(container.querySelector("[data-filled=true]")).toHaveClass("bg-success-bar");
  });

  it("names the bar when the value text is hidden", () => {
    render(<ScoreBar score={4} hideValue valueText="4 von 5" />);

    expect(screen.getByRole("img", { name: "4 von 5" })).toBeInTheDocument();
  });
});
