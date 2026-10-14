import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, Panel } from "./Panel";

describe("Panel", () => {
  it("is a region labelled by its heading, with actions and description", () => {
    render(
      <Panel title="Processing now" description="Median turnaround 18 min" actions={<button>Refresh</button>}>
        body
      </Panel>,
    );

    const region = screen.getByRole("region", { name: "Processing now" });
    expect(screen.getByRole("heading", { level: 2, name: "Processing now" })).toBeInTheDocument();
    expect(region).toHaveTextContent("Median turnaround 18 min");
    expect(region).toHaveClass("rounded-panel", "border-line", "px-5");
  });

  it("puts the heading in a divided bar and shows a footer when flush", () => {
    render(
      <Panel flush title="Recent recordings" footer={<span>Showing 7 of 214</span>}>
        <table />
      </Panel>,
    );

    const heading = screen.getByRole("heading", { name: "Recent recordings" });
    expect(heading.parentElement?.parentElement).toHaveClass("border-b");
    expect(screen.getByText("Showing 7 of 214")).toBeInTheDocument();
    expect(screen.getByRole("region")).not.toHaveClass("px-5");
  });
});

describe("Card", () => {
  it("applies the tone", () => {
    render(
      <Card tone="warning" as="article">
        Needs review
      </Card>,
    );

    expect(screen.getByRole("article")).toHaveClass("bg-warning-surface", "border-warning-border", "rounded-card");
  });
});
