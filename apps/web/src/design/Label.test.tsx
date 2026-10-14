import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Label } from "./Label";

describe("Label", () => {
  it("names the control it points at", () => {
    render(
      <>
        <Label htmlFor="school">School name</Label>
        <input id="school" />
      </>,
    );

    expect(screen.getByRole("textbox", { name: "School name" })).toBeInTheDocument();
  });
});
