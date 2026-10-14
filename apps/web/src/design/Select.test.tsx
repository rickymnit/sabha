import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Select } from "./Select";

describe("Select", () => {
  it("is labelled and changes value", async () => {
    render(
      <Select label="Campus" defaultValue="main">
        <option value="main">Main campus</option>
        <option value="vn">Vaishali Nagar</option>
      </Select>,
    );
    const select = screen.getByRole("combobox", { name: "Campus" });

    expect(select).toHaveValue("main");
    await userEvent.setup().selectOptions(select, "vn");
    expect(select).toHaveValue("vn");
  });

  it("describes an error", () => {
    render(
      <Select label="Language" error="Pick a language.">
        <option>Hindi</option>
      </Select>,
    );

    expect(screen.getByRole("combobox", { name: "Language" })).toHaveAccessibleDescription("Pick a language.");
  });
});
