import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AnalysisVersion, BulkReanalysisRequest } from "../../api/types";
import { BulkReanalyseDialog } from "./BulkReanalyseDialog";
import { ReanalyseDialog } from "./ReanalyseDialog";
import { VersionPicker } from "./VersionPicker";

const version = (id: string, created_at: string, rubric_version: string, superseded: boolean): AnalysisVersion => ({
  id, version: id, status: "COMPLETED", overall_score: 3.5, rubric_id: `teaching.school.v${rubric_version}`,
  rubric_version, superseded, created_at,
}); // prettier-ignore

describe("ReanalyseDialog", () => {
  it("needs a reason, then starts and closes", async () => {
    const onSubmit = vi.fn(async () => {});
    const onClose = vi.fn();
    render(<ReanalyseDialog recordingWord="lesson" onSubmit={onSubmit} onClose={onClose} />);
    expect(screen.getByRole("dialog", { name: "Re-analyse this lesson" })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Re-analyse" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Say why");
    await user.type(screen.getByRole("textbox", { name: "Why" }), "Rubric v0.2 is out.");
    await user.click(screen.getByRole("button", { name: "Re-analyse" }));
    expect(onSubmit).toHaveBeenCalledWith("Rubric v0.2 is out.");
    expect(onClose).toHaveBeenCalled();
  });
});

describe("BulkReanalyseDialog", () => {
  it("counts first, then starts at most 100 with the reason", async () => {
    const run = vi.fn(async (request: BulkReanalysisRequest) =>
      request.dry_run
        ? { rubric_id: "teaching.school.v0.2", matching: 140, started: 0, remaining: 140 }
        : { rubric_id: "teaching.school.v0.2", matching: 140, started: 100, remaining: 40 },
    );
    const onStarted = vi.fn();
    render(
      <BulkReanalyseDialog types={["teaching", "reception"]} recordingsWord="lessons" typeLabel={(t) => t}
        run={run} onStarted={onStarted} onClose={vi.fn()} />, // prettier-ignore
    );
    expect(await screen.findByText(/140 finished lessons were scored with an older rubric/)).toBeInTheDocument();
    expect(screen.getByText(/The first 100 start now/)).toBeInTheDocument();
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ type: "teaching", dry_run: true }));
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Why" }), "New rubric.");
    await user.click(screen.getByRole("button", { name: "Re-analyse 100" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(expect.objectContaining({ started: 100 })));
    expect(run).toHaveBeenLastCalledWith({ type: "teaching", reason: "New rubric.", dry_run: false });
  });

  it("says when nothing needs it, and cannot start", async () => {
    const run = vi.fn(async () => ({ rubric_id: "r", matching: 0, started: 0, remaining: 0 }));
    render(
      <BulkReanalyseDialog types={["teaching"]} recordingsWord="lessons" typeLabel={() => "Teaching"} run={run}
        onStarted={vi.fn()} onClose={vi.fn()} />, // prettier-ignore
    );
    expect(await screen.findByText(/already use the current rubric/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-analyse" })).toBeDisabled();
  });
});

describe("VersionPicker", () => {
  const versions = [
    version("new", "2026-10-26T05:00:00Z", "0.2", false),
    version("old", "2026-10-20T05:00:00Z", "0.1", true),
  ];

  it("lists every version, newest first, and picks an earlier one", async () => {
    const onSelect = vi.fn();
    render(<VersionPicker versions={versions} selected={undefined} onSelect={onSelect} />);
    const picker = screen.getByRole("combobox", { name: "Analysis" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      expect.stringContaining("rubric v0.2 (latest)"),
      expect.stringContaining("rubric v0.1"),
    ]);
    await userEvent.setup().selectOptions(picker, "old");
    expect(onSelect).toHaveBeenCalledWith("old");
  });

  it("is hidden while there is only one version", () => {
    const { container } = render(
      <VersionPicker versions={versions.slice(0, 1)} selected={undefined} onSelect={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
