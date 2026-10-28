import { describe, expect, it } from "vitest";

import { unitLabel, unitTree } from "./units";

describe("unitTree", () => {
  it("puts units without a number first, then numbered ones by number, each with its own units", () => {
    const units = [
      { id: "c10", name: "Class 10" },
      { id: "c2", name: "Class 2" },
      { id: "ukg", name: "UKG" },
      { id: "lkg", name: "LKG" },
      { id: "c11", name: "Class 11" },
      { id: "pcm", name: "PCM", parent_id: "c11" },
      { id: "com", name: "Commerce", parent_id: "c11" },
    ];
    expect(unitTree(units).map((u) => u.name)).toEqual(["LKG", "UKG", "Class 2", "Class 10", "Class 11"]);
    expect(
      unitTree(units)
        .at(-1)
        ?.children.map((u) => u.name),
    ).toEqual(["Commerce", "PCM"]);
    expect(unitLabel(units, "pcm")).toBe("Class 11 · PCM");
  });
});
