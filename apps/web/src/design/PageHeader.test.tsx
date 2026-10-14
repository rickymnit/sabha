import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("renders the h1, subtitle and actions", () => {
    render(<PageHeader title="Overview" description="All campuses" actions={<button>Upload</button>} />);

    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toHaveClass("text-title");
    expect(screen.getByText("All campuses")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });

  it("renders breadcrumbs with the last one as the current page", () => {
    render(
      <PageHeader
        title="Upload recordings"
        titleAs="h2"
        breadcrumbs={[{ label: "Recordings", href: "/recordings" }, { label: "Upload" }]}
      />,
    );

    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByRole("link", { name: "Recordings" })).toHaveAttribute("href", "/recordings");
    expect(within(nav).getByText("Upload")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 2, name: "Upload recordings" })).toBeInTheDocument();
  });
});
