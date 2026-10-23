import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { coachingItems, overviewMetrics } from "./metrics";
import { emptyOverview, mockLabels, mockOverview, mockTypeNames } from "./mock";
import { OverviewPage, type OverviewPageProps } from "./OverviewPage";
import type { OverviewStats } from "./types";

const NOW = () => new Date("2026-10-16T05:00:00Z");

function renderPage(stats: OverviewStats | undefined, overrides: Partial<OverviewPageProps> = {}) {
  const onRangeChange = vi.fn();
  render(
    <OverviewPage
      stats={stats}
      scopeLabel="All campuses"
      preset="7d"
      range={{ start: "2026-10-06", end: "2026-10-12" }}
      onRangeChange={onRangeChange}
      typeNames={mockTypeNames}
      labels={mockLabels}
      rubricHref={(id) => `/rubrics/${id}`}
      now={NOW}
      {...overrides}
    />,
  );
  return { onRangeChange, user: userEvent.setup() };
}

const strip = () => screen.getByRole("region", { name: "In this period" });

describe("overview metrics", () => {
  it("shows the headline numbers with their labels from the tenant", () => {
    renderPage(mockOverview());
    expect(screen.getByText("All campuses, 6 to 12 October 2026")).toBeInTheDocument();
    const cells = within(strip());
    expect(cells.getByText("Lessons analysed").nextSibling).toHaveTextContent("214");
    expect(cells.getByText("Audio processed").nextSibling).toHaveTextContent("162 h");
    expect(cells.getByText("41.2 h of silence removed")).toBeInTheDocument();
    expect(cells.getByText("Median teaching score").nextSibling).toHaveTextContent("3.5 / 5");
    expect(cells.getByText("From 128 lessons")).toBeInTheDocument();
    expect(cells.getByRole("link", { name: "Review disputes" })).toHaveAttribute("href", "/reviews");
  });

  it("hides a median whose n is 0 instead of showing 0", () => {
    renderPage(mockOverview());
    expect(within(strip()).queryByText("Median sales score")).toBeNull();
  });

  it("shows an empty state, not zeros, when nothing was analysed", () => {
    renderPage(emptyOverview());
    expect(screen.queryByText("Audio processed")).toBeNull();
    expect(screen.getByText("No lessons analysed in this period")).toBeInTheDocument();
    expect(screen.queryByText("0")).toBeNull();
    expect(overviewMetrics(emptyOverview(), mockTypeNames, mockLabels)).toEqual([]);
  });

  it("shows a placeholder while loading", () => {
    renderPage(undefined);
    expect(screen.queryByRole("region", { name: "In this period" })).toBeNull();
    expect(screen.queryByText("Where coaching helps most")).toBeNull();
  });
});

describe("where coaching helps most", () => {
  it("lists dimensions with data, lowest first, with n and a link to the rubric", () => {
    renderPage(mockOverview());
    const panel = screen.getByRole("region", { name: "Where coaching helps most" });
    const items = within(panel).getAllByRole("listitem");
    expect(items.map((li) => within(li).getByRole("link").textContent)).toEqual([
      "Checks for understanding",
      "Recap and closure",
      "Resolution confirmed",
    ]);
    expect(within(items[0]!).getByText("Teaching, 128 lessons")).toBeInTheDocument();
    expect(within(items[0]!).getByRole("link")).toHaveAttribute("href", "/rubrics/teaching.school.v1.0");
    expect(within(panel).queryByText("Objection handling")).toBeNull(); // n = 0
  });

  it("keeps at most four items", () => {
    const many = Array.from({ length: 6 }, (_, i) => ({
      rubric_id: "r",
      dimension_key: `d${i}`,
      dimension_name: `D${i}`,
      type: "teaching" as const,
      median: 3 - i / 10,
      n: 10,
    }));
    expect(coachingItems(many).map((i) => i.dimension_key)).toEqual(["d5", "d4", "d3", "d2"]);
  });

  it("says so when there is not enough data", () => {
    renderPage(emptyOverview());
    expect(screen.getByText("Not enough verified scores in this period yet.")).toBeInTheDocument();
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

describe("overview with what the API serves today", () => {
  it("leaves out numbers the API does not send, and writes the tenant's capitalised words in lower case", () => {
    const stats = { ...mockOverview(), silence_removed_hours: undefined, open_disputes: undefined };
    const labels = { ...mockLabels, recording: "Lesson", recording_plural: "Lessons" };
    renderPage(stats, { labels, rubricHref: undefined });
    expect(screen.queryByText(/silence removed/)).toBeNull();
    expect(screen.queryByText("Open disputes")).toBeNull();
    expect(within(strip()).getByText("From 128 lessons")).toBeInTheDocument();
    expect(screen.queryAllByRole("link")).toHaveLength(0); // no rubric page yet: dimension names are plain text
  });
});
