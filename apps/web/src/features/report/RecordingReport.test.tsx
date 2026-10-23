import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installMediaMock, loadMetadata } from "../../test/media";
import type { PlaybackUrl } from "../transcript";
import { RecordingReport } from "./RecordingReport";
import { visibleDimensions } from "./visibility";
import { mockLesson, mockReport } from "./mock";
import type { AnalysisReport, Dimension, ViewerRole } from "./types";

let media: ReturnType<typeof installMediaMock>;
beforeEach(() => {
  media = installMediaMock();
});
afterEach(() => media.restore());

const lesson = mockLesson();
const getPlaybackUrl = vi.fn(async (): Promise<PlaybackUrl> => ({
  url: "https://audio.example/playback.opus?sig=1",
  expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
}));

async function renderReport(analysis: AnalysisReport, viewerRole: ViewerRole = "admin") {
  const view = render(
    <RecordingReport
      recording={lesson.recording}
      analysis={analysis}
      transcript={lesson.transcript}
      labels={lesson.labels}
      roles={lesson.roles}
      viewerRole={viewerRole}
      getPlaybackUrl={getPlaybackUrl}
    />,
  );
  await act(async () => {});
  const audio = view.container.querySelector("audio") as HTMLAudioElement;
  loadMetadata(audio, lesson.transcript.utterances.at(-1)!.end_ms / 1000 + 1);
  return { ...view, audio };
}

const pinLabels = () =>
  within(screen.getByTestId("timeline-track"))
    .queryAllByRole("button", { name: /^Play evidence/ })
    .map((b) => b.getAttribute("aria-label"));

describe("visibleDimensions (golden rule 5 in the UI)", () => {
  const verified: Dimension = {
    key: "a",
    name: "A",
    weight: 0.5,
    verified: true,
    score: 4,
    rationale: "r",
    evidence: [{ quote: "q", utterance_id: "u0001", start_ms: 0, end_ms: 1 }],
  } as Dimension;

  it("keeps a verified dimension with a score and quotes", () => {
    expect(visibleDimensions([verified])).toHaveLength(1);
  });

  it.each([
    ["unverified", { verified: false }],
    ["no score", { score: null }],
    ["score out of range", { score: 7 }],
    ["no quotes", { evidence: [] }],
  ])("drops a dimension with %s, whatever else it carries", (_label, change) => {
    expect(visibleDimensions([{ ...verified, ...change } as Dimension])).toHaveLength(0);
  });
});

describe("RecordingReport", () => {
  it("never shows a score or quote of an unverified dimension, even if the payload carries one", async () => {
    const report = mockReport(lesson, "completed");
    const [first, ...rest] = report.dimensions;
    // A forged payload: marked unverified but still carrying a score and evidence.
    const forged = { ...first, verified: false } as Dimension;
    await renderReport({ ...report, dimensions: [forged, ...rest] });

    const scores = screen.getByRole("region", { name: "Rubric scores" });
    expect(within(scores).queryByText(first!.name)).toBeNull();
    for (const quote of "evidence" in first! ? first.evidence : []) {
      expect(screen.queryByText(quote.quote, { exact: false })).toBeNull();
    }
  });

  it("selecting a dimension moves the evidence pins", async () => {
    const report = mockReport(lesson, "completed");
    await renderReport(report);
    const user = userEvent.setup();
    const before = pinLabels();
    const buttons = within(screen.getByRole("region", { name: "Rubric scores" })).getAllByRole("button");
    const other = buttons.find((b) => b.getAttribute("aria-pressed") === "false")!;

    await user.click(other);

    expect(other).toHaveAttribute("aria-pressed", "true");
    expect(pinLabels()).not.toEqual(before);
    expect(pinLabels().length).toBeGreaterThan(0);
  });

  it("clicking an evidence quote seeks the audio to the quote", async () => {
    const report = mockReport(lesson, "completed");
    const { audio } = await renderReport(report);
    const user = userEvent.setup();
    const selectedKey = within(screen.getByRole("region", { name: "Rubric scores" }))
      .getAllByRole("button")
      .find((b) => b.getAttribute("aria-pressed") === "true")!;
    const dimension = visibleDimensions(report.dimensions).find((d) => selectedKey.textContent?.includes(d.name))!;
    const firstQuote = dimension.evidence[0]!;

    const pin = within(screen.getByTestId("timeline-track")).getAllByRole("button", { name: /^Play evidence 1/ })[0]!;
    await user.click(pin);
    await act(async () => {});

    expect(audio.currentTime).toBeCloseTo(firstQuote.start_ms / 1000, 3);
  });

  it("tells admins which dimensions were hidden, and staff nothing", async () => {
    const partial = mockReport(lesson, "partial");
    const hidden = partial.dimensions.filter((d) => !d.verified).map((d) => d.name);
    expect(hidden.length).toBeGreaterThan(0);

    const admin = await renderReport(partial, "admin");
    expect(screen.getByText(/could not be verified in the transcript/)).toBeInTheDocument();
    admin.unmount();

    await renderReport(partial, "staff");
    expect(screen.queryByText(/could not be verified in the transcript/)).toBeNull();
    for (const name of hidden) expect(screen.queryByText(name)).toBeNull();
  });
});

describe("RecordingReport disputes and reviewed scores (P6.7)", () => {
  it("shows no dispute button to viewers who may not dispute", async () => {
    await renderReport(mockReport(lesson, "completed"));
    expect(screen.queryByRole("button", { name: "Dispute this score" })).toBeNull();
  });

  it("opens the dispute dialog for the person analysed", async () => {
    const onSubmitDispute = vi.fn(async () => {});
    render(
      <RecordingReport
        recording={lesson.recording}
        analysis={mockReport(lesson, "completed")}
        transcript={lesson.transcript}
        labels={lesson.labels}
        roles={lesson.roles}
        viewerRole="staff"
        getPlaybackUrl={getPlaybackUrl}
        canDispute
        onSubmitDispute={onSubmitDispute}
      />,
    );
    await act(async () => {});
    await userEvent.setup().click(screen.getByRole("button", { name: "Dispute this score" }));
    expect(screen.getByRole("dialog", { name: "Dispute a score" })).toBeInTheDocument();
  });

  it("shows a reviewer's score with a marker and keeps the AI score as history", async () => {
    const report = mockReport(lesson, "completed");
    const [first] = visibleDimensions(report.dimensions);
    const reviewed = {
      ...first!,
      override: {
        score: 5,
        reviewer_role: "academic head",
        note: "Clear checks.",
        resolved_at: "2026-10-16T05:00:00Z",
      },
    };
    await renderReport({ ...report, dimensions: report.dimensions.map((d) => (d.key === first!.key ? reviewed : d)) });
    const scores = screen.getByRole("region", { name: "Rubric scores" });
    await userEvent.setup().click(within(scores).getByRole("button", { name: new RegExp(first!.name) }));
    expect(within(scores).getByText("Reviewed")).toBeInTheDocument();
    expect(screen.getByTestId("override-note")).toHaveTextContent(`AI score was ${first!.score}`);
  });

  it("shows a not-applicable dimension as a note, never as a score or a hidden one", async () => {
    const report = mockReport(lesson, "completed");
    const [first] = visibleDimensions(report.dimensions);
    const escalation: Dimension = {
      key: "escalation_handling",
      name: "Escalation handling",
      weight: 0.1,
      verified: true,
      not_applicable: true,
      score: null,
      rationale: "The call had nothing to escalate.",
      evidence: first!.evidence,
    };
    await renderReport({ ...report, dimensions: [...report.dimensions, escalation] }, "admin");
    expect(screen.getByTestId("not-applicable-note")).toHaveTextContent("Escalation handling");
    expect(screen.getByTestId("not-applicable-note")).toHaveTextContent("The call had nothing to escalate.");
    expect(within(screen.getByRole("region", { name: "Rubric scores" })).queryByText("Escalation handling")).toBeNull();
    expect(screen.queryByTestId("admin-hidden-note")?.textContent ?? "").not.toContain("Escalation handling");
  });
});
