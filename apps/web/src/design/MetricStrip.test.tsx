import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricStrip } from "./MetricStrip";

describe("MetricStrip", () => {
  it("lists each metric as a term and value in a named region", () => {
    render(
      <MetricStrip
        label="This week"
        metrics={[
          { id: "a", label: "Recordings analysed", value: "214", foot: "32 more", footTone: "success" },
          { id: "b", label: "Audio processed", value: "162 h" },
          { id: "c", label: "Median score", value: "3.5", suffix: " / 5" },
          { id: "d", label: "Disputed", value: "7", foot: <a href="#">Review disputes</a> },
        ]}
      />,
    );

    const region = screen.getByRole("region", { name: "This week" });
    expect(
      within(region)
        .getAllByRole("term")
        .map((t) => t.textContent),
    ).toEqual(["Recordings analysed", "Audio processed", "Median score", "Disputed"]);
    expect(screen.getByText("214")).toHaveClass("text-metric", "tabular-nums");
    expect(screen.getByText("3.5", { exact: false })).toHaveTextContent("3.5 / 5");
    expect(screen.getByText("32 more")).toHaveClass("text-success");
    expect(screen.getByRole("link", { name: "Review disputes" })).toBeInTheDocument();
  });
});
