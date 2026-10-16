import { describe, expect, it } from "vitest";

import { addDays, describeRange, istToday, presetRange, rangeProblem, toQuery } from "./range";

// 16 Oct 2026, 20:00 UTC is already 17 Oct 01:30 in India.
const LATE_EVENING_UTC = new Date("2026-10-16T20:00:00Z");
const MORNING_UTC = new Date("2026-10-16T05:00:00Z");

describe("IST days", () => {
  it("uses the Indian calendar day, not the UTC one", () => {
    expect(istToday(MORNING_UTC)).toBe("2026-10-16");
    expect(istToday(LATE_EVENING_UTC)).toBe("2026-10-17");
  });

  it("adds days across month and year ends", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2027-01-01", -1)).toBe("2026-12-31");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
  });
});

describe("presets", () => {
  it("include today", () => {
    expect(presetRange("7d", MORNING_UTC)).toEqual({ start: "2026-10-10", end: "2026-10-16" });
    expect(presetRange("30d", MORNING_UTC)).toEqual({ start: "2026-09-17", end: "2026-10-16" });
    expect(presetRange("month", MORNING_UTC)).toEqual({ start: "2026-10-01", end: "2026-10-16" });
    expect(presetRange("7d", LATE_EVENING_UTC).end).toBe("2026-10-17");
  });
});

describe("toQuery", () => {
  it("sends IST midnights as UTC instants, end exclusive", () => {
    expect(toQuery({ start: "2026-10-06", end: "2026-10-12" })).toEqual({
      from: "2026-10-05T18:30:00.000Z",
      to: "2026-10-12T18:30:00.000Z",
    });
  });
});

describe("custom ranges", () => {
  it("accept a valid range", () => {
    expect(rangeProblem({ start: "2026-10-01", end: "2026-10-16" }, MORNING_UTC)).toBeNull();
  });

  it.each([
    [{ start: "", end: "2026-10-16" }, "Choose both dates."],
    [{ start: "2026-02-30", end: "2026-10-16" }, "Choose both dates."],
    [{ start: "2026-10-10", end: "2026-10-01" }, "on or before"],
    [{ start: "2026-10-01", end: "2026-10-17" }, "future"],
    [{ start: "2025-01-01", end: "2026-10-16" }, "at most 366 days"],
  ])("refuse %j", (range, message) => {
    expect(rangeProblem(range, MORNING_UTC)).toContain(message);
  });
});

describe("describeRange", () => {
  it.each([
    [{ start: "2026-10-06", end: "2026-10-12" }, "6 to 12 October 2026"],
    [{ start: "2026-09-28", end: "2026-10-04" }, "28 September to 4 October 2026"],
    [{ start: "2026-12-28", end: "2027-01-03" }, "28 December 2026 to 3 January 2027"],
    [{ start: "2026-10-12", end: "2026-10-12" }, "12 October 2026"],
  ])("%j reads %s", (range, text) => {
    expect(describeRange(range)).toBe(text);
  });
});
