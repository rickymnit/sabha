import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Skeleton, SkeletonGroup } from "./Skeleton";

describe("Skeleton", () => {
  it("is hidden from assistive technology and shimmers only with motion allowed", () => {
    const { container } = render(<Skeleton className="h-8 w-8" />);

    const block = container.firstElementChild;
    expect(block).toHaveAttribute("aria-hidden", "true");
    expect(block).toHaveClass("bg-track", "motion-safe:animate-shimmer", "h-8");
    expect(block?.className).not.toMatch(/(^|\s)animate-/);
  });

  it("sits in a busy container that tells screen readers what is loading", () => {
    render(
      <SkeletonGroup label="Loading recordings">
        <Skeleton />
      </SkeletonGroup>,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Loading recordings");
    expect(status.parentElement).toHaveAttribute("aria-busy", "true");
  });
});
