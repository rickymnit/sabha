import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("shows a heading, description, decorative icon and action", () => {
    render(
      <EmptyState
        headingAs="h3"
        icon={<svg data-testid="icon" />}
        title="No recordings yet"
        description="Upload one to start."
        action={<button>Upload</button>}
      />,
    );

    expect(screen.getByRole("heading", { level: 3, name: "No recordings yet" })).toBeInTheDocument();
    expect(screen.getByText("Upload one to start.")).toBeInTheDocument();
    expect(screen.getByTestId("icon").parentElement).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });
});
