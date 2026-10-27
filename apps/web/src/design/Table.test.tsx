import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Table, type TableColumn } from "./Table";

interface Row {
  id: string;
  name: string;
  score: string;
}

const columns: TableColumn<Row>[] = [
  { key: "name", header: "Name", render: (r) => r.name },
  { key: "score", header: "Score", align: "right", render: (r) => r.score },
  { key: "pdf", header: "Download", hideHeader: true, render: () => <a href="#">PDF</a> },
];
const rows: Row[] = [
  { id: "1", name: "Concept clarity", score: "4" },
  { id: "2", name: "Pacing", score: "3" },
];

describe("Table", () => {
  it("has a caption, column headers and one row per item", () => {
    render(<Table caption="Rubric scores" columns={columns} rows={rows} rowKey={(r) => r.id} />);

    const table = screen.getByRole("table", { name: "Rubric scores" });
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual(["Name", "Score", "Download"]);
    for (const h of headers) expect(h).toHaveAttribute("scope", "col");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("Download")).toHaveClass("sr-only");
    expect(within(table).getByRole("cell", { name: "4" })).toHaveClass("text-right");
  });

  it("sits in a focusable, named region that scrolls sideways", () => {
    render(<Table aria-label="Invoices" minWidth={520} columns={columns} rows={rows} rowKey={(r) => r.id} />);

    // Named apart from the table (and the panel around it), so landmarks stay unique (axe landmark-unique).
    const region = screen.getByRole("region", { name: "Invoices table" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region).toHaveClass("overflow-x-auto", "relative");
    expect(screen.getByRole("table", { name: "Invoices" })).toHaveStyle({ minWidth: "520px" });
  });

  it("shows the empty message across all columns", () => {
    render(<Table aria-label="Invoices" columns={columns} rows={[]} rowKey={(r) => r.id} empty="No invoices yet" />);

    expect(screen.getByRole("cell", { name: "No invoices yet" })).toHaveAttribute("colspan", "3");
  });
});
