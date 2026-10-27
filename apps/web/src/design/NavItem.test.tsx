import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NavItem } from "./NavItem";

describe("NavItem", () => {
  it("marks the current page and is a 44px row", () => {
    render(
      <NavItem href="/recordings" current icon={<svg />}>
        Recordings
      </NavItem>,
    );

    const link = screen.getByRole("link", { name: "Recordings" });
    expect(link).toHaveAttribute("aria-current", "page");
    expect(link).toHaveAttribute("href", "/recordings");
    expect(link).toHaveClass("min-h-touch", "bg-primary-tint", "text-primary");
  });

  it("reads the badge with its label, and shows type counts", () => {
    render(
      <>
        <NavItem href="/reviews" badge={7} badgeLabel="7 waiting">
          Reviews
        </NavItem>
        <NavItem href="/t" type="teaching" count={128}>
          Teaching
        </NavItem>
      </>,
    );

    expect(screen.getByRole("link", { name: "Reviews, 7 waiting" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Teaching, 128" }).querySelector(".bg-type-teaching")).not.toBeNull();
  });
});
