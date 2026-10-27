import { describe, expect, it } from "vitest";

import { scoreBand } from "./score";

describe("scoreBand (v2 rule, on the one-decimal value shown)", () => {
  it.each([
    [1, "low"],
    [2.94, "low"],
    [2.96, "mid"],
    [3, "mid"],
    [3.7, "mid"],
    [3.74, "mid"],
    [3.75, "good"],
    [3.8, "good"],
    [5, "good"],
  ] as const)("%s is %s", (score, band) => {
    expect(scoreBand(score)).toBe(band);
  });
});
