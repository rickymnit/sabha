import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusChip } from "./StatusChip";
import type { RecordingStatus } from "./types";

const cases: [RecordingStatus, string, string[]][] = [
  ["analysed", "Analysed", ["bg-success-tint", "text-success"]],
  ["transcribing", "Transcribing", ["bg-primary-tint", "text-primary-hover"]],
  ["analysing", "Analysing", ["bg-primary-tint", "text-primary-hover"]],
  ["needs-review", "Needs review", ["bg-warning-tint", "text-warning-ink"]],
  ["failed", "Failed", ["bg-danger-tint", "text-danger"]],
  ["uploading", "Uploading", ["bg-primary-tint", "text-primary-hover"]],
];

describe("StatusChip", () => {
  it.each(cases)("shows %s as text, not colour alone", (status, text, classes) => {
    render(<StatusChip status={status} />);

    const chip = screen.getByText(text);
    expect(chip).toHaveClass(...classes);
    // The dot is decorative.
    expect(chip.querySelector("[aria-hidden=true]")).not.toBeNull();
  });

  it("takes its text from props", () => {
    render(<StatusChip status="analysed">Live</StatusChip>);

    expect(screen.getByText("Live")).toHaveClass("bg-success-tint");
  });
});
