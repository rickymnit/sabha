import { describe, expect, it } from "vitest";

import { scoreBand } from "./score";

describe("scoreBand (report-screen rule)", () => {
  it.each([
    [1, "low"],
    [2.99, "low"],
    [3, "mid"],
    [3.5, "mid"],
    [3.99, "mid"],
    [4, "good"],
    [5, "good"],
  ] as const)("%s is %s", (score, band) => {
    expect(scoreBand(score)).toBe(band);
  });
});
