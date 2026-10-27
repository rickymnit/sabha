import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ALL_UNITS, coachingRows, overviewTiles } from "./metrics";
import { emptyOverview, mockLabels, mockOverview, mockTypeNames } from "./mock";
import { OverviewPage, type OverviewPageProps } from "./OverviewPage";
import type { OverviewStats } from "./types";

const NOW = () => new Date("2026-10-16T05:00:00Z");
const tiles = (stats: OverviewStats, types: OverviewPageProps["enabledTypes"] = ["teaching", "reception"]) =>
  Object.fromEntries(overviewTiles(stats, mockTypeNames, mockLabels, "last week", types).map((t) => [t.id, t]));

function renderPage(stats: OverviewStats | undefined, overrides: Partial<OverviewPageProps> = {}) {
  const onRangeChange = vi.fn();
  render(
    <OverviewPage
      stats={stats}
      name="Priya"
      preset="7d"
      range={{ start: "2026-10-06", end: "2026-10-12" }}
      onRangeChange={onRangeChange}
      compare="last week"
      unit={ALL_UNITS}
      onUnitChange={vi.fn()}
      typeNames={mockTypeNames}
      labels={mockLabels}
      enabledTypes={["teaching", "reception"]}
      now={NOW}
      {...overrides}
    />,
  );
  return { onRangeChange, user: userEvent.setup() };
}

describe("overview tiles", () => {
  it("compares with the previous period and draws one bar per period", () => {
    const t = tiles(mockOverview());
    expect(t.analysed).toMatchObject({ value: "214", foot: "Up 32 on last week", footTone: "good" });
    expect(t.analysed?.bars).toHaveLength(8);
    expect(t.analysed?.bars.at(-1)).toBe(1); // the busiest period is the full height
    expect(t.audio?.foot).toBe("41.2 h of silence skipped");
    expect(t["median-teaching"]).toMatchObject({ value: "3.5", foot: "Up 0.2 on last week" });
    expect(t.resolved).toMatchObject({ value: "81", foot: "Down 3 points on last week", footTone: "bad" });
  });

  it("leaves out what has no data instead of showing 0", () => {
    expect(tiles(emptyOverview())).toEqual({});
    const t = tiles({ ...mockOverview(), silence_n: 0, tickets: 0 });
    expect(t.audio?.foot).toBeUndefined();
    expect(t.resolved).toBeUndefined();
    expect(tiles(mockOverview(), ["teaching"]).resolved).toBeUndefined(); // reception not switched on
  });

  it("puts the main type's weakest rubric points first in the coaching table", () => {
    expect(coachingRows(mockOverview()).map((r) => r.dimension_key)).toEqual(["cfu", "recap"]);
  });
});

describe("period picker", () => {
  it("applies a preset in India time", async () => {
    const { onRangeChange, user } = renderPage(mockOverview());
    await user.selectOptions(screen.getByLabelText("Period"), "30d");
    expect(onRangeChange).toHaveBeenCalledWith("30d", { start: "2026-09-17", end: "2026-10-16" });
  });

  it("checks a custom range before applying it", async () => {
    const { onRangeChange, user } = renderPage(mockOverview(), { preset: "custom" });
    const from = screen.getByLabelText("From");
    await user.clear(from);
    await user.type(from, "2026-10-14");
    expect(screen.getByText("The start date must be on or before the end date.")).toBeInTheDocument();
    expect(onRangeChange).not.toHaveBeenCalled();
    await user.clear(from);
    await user.type(from, "2026-10-01");
    expect(onRangeChange).toHaveBeenLastCalledWith("custom", { start: "2026-10-01", end: "2026-10-12" });
  });
});
