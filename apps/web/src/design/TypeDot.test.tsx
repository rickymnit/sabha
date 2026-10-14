import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TypeDot } from "./TypeDot";
import type { ConversationType } from "./types";

describe("TypeDot", () => {
  it.each<[ConversationType, string]>([
    ["teaching", "bg-type-teaching"],
    ["reception", "bg-type-reception"],
    ["counselling", "bg-type-counselling"],
    ["meeting", "bg-type-meeting"],
    ["sales", "bg-type-sales"],
  ])("colours %s with its token", (type, swatch) => {
    const { container } = render(<TypeDot type={type} />);

    expect(container.querySelector(`.${swatch}`)).toHaveAttribute("aria-hidden", "true");
  });

  it("shows the label it is given", () => {
    render(<TypeDot type="meeting" label="Staff meeting" />);

    expect(screen.getByText("Staff meeting")).toBeInTheDocument();
  });
});
