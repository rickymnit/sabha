import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "./Field";

describe("Field", () => {
  it("renders the label for the control and ids for hint and error", () => {
    render(
      <Field id="notes" label="Notes" hint="Optional" error="Too long">
        <textarea id="notes" aria-describedby="notes-hint notes-error" />
      </Field>,
    );

    expect(screen.getByRole("textbox", { name: "Notes" })).toHaveAccessibleDescription("Optional Too long");
  });
});
