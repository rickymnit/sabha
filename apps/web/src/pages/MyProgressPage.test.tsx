// A staff member's own page: a sales rep with reports, and a new teacher with nothing uploaded yet. The API decides
// what anyone may read; these check what the page makes of it (own words, no organisation cost tile, the manager's
// note, at most three points to work on).

import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/queries";
import { routes } from "../app/routes";
import { ToastProvider } from "../design";
import { emptyOverview } from "../features/overview/mock";
import type { OverviewStats } from "../features/overview/types";
import { StaticSessionProvider } from "../session/providers";
import type { Session } from "../session/session";

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

function stubApi(answers: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const key = Object.keys(answers)
        .filter((prefix) => path.startsWith(prefix))
        .sort((a, b) => b.length - a.length)[0];
      return key ? json(answers[key]) : new Response(null, { status: 404 });
    }),
  );
}

function renderAt(path: string) {
  const session: Session = { mode: "dev", token: "t", ready: true, signOut: vi.fn() };
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <StaticSessionProvider session={session}>
      <ToastProvider>
        <QueryClientProvider client={createQueryClient()}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ToastProvider>
    </StaticSessionProvider>,
  );
  return router;
}

const salesRep = {
  user: { id: "u-r", email: "r@x", name: "Rohan Mehta", role: "staff", title: null, unit_ids: [] },
  tenant: { id: "t", name: "Brightpath Software", profile: "company", enabled_types: ["sales", "support"], units: [],
            labels: { person: "Team member", person_plural: "Team members", recording: "Conversation",
                      recording_plural: "Conversations", unit: "Team", manager: "Manager" } }, // prettier-ignore
};

const teacher = {
  user: { id: "u-t", email: "t@x", name: "Meena Iyer", role: "staff", title: null, unit_ids: [] },
  tenant: { id: "t", name: "Demo School", profile: "school", enabled_types: ["teaching"], units: [],
            labels: { person: "Teacher", person_plural: "Teachers", recording: "Lesson",
                      recording_plural: "Lessons", unit: "Class", manager: "Coordinator" } }, // prettier-ignore
};

const dim = (key: string, name: string, median: number) => ({
  rubric_id: "sales.company.v0.2", dimension_key: key, dimension_name: name, type: "sales", median, n: 4,
  weekly: [{ from: "2026-10-20T00:00:00Z", median: median - 0.5, n: 2 }, { from: "2026-10-27T00:00:00Z", median, n: 2 }],
}); // prettier-ignore

function salesOverview(): OverviewStats {
  const period = { ...emptyOverview(), recordings_analysed: 4, audio_hours: 2.5,
                   median_overall_by_type: [{ type: "sales" as const, median: 3.4, n: 4 }] }; // prettier-ignore
  return {
    ...period,
    units: [],
    series: [{ ...period, recordings_analysed: 3, median_overall_by_type: [{ type: "sales", median: 3.1, n: 3 }] }, period], // prettier-ignore
    coaching: [
      dim("discovery", "Discovery questions", 2.4),
      dim("next_step", "Agreed next step", 3.9),
      dim("objections", "Objection handling", 2.8),
      dim("demo", "Demo tied to needs", 3.1),
    ] as OverviewStats["coaching"],
    processing: [],
  };
}

const call = {
  id: "r1", title: "Acme renewal call", type: "sales", status: "COMPLETED", status_reason: null, status_note: null,
  person: { id: "p-r", name: "Rohan Mehta" }, unit_id: null, file_name: "acme.m4a", duration_ms: 1_800_000,
  created_at: "2026-11-09T05:00:00Z", status_changed_at: null, completed_at: "2026-11-09T05:10:00Z",
  overall_score: 3.4, audio_deleted_at: null, shared_at: "2026-11-09T09:00:00Z",
}; // prettier-ignore

afterEach(() => vi.unstubAllGlobals());

describe("my progress", () => {
  it("shows a sales rep their own numbers, their manager's note, what to try next and three points to work on", async () => {
    stubApi({
      "/v1/me": salesRep,
      "/v1/overview": salesOverview(),
      "/v1/recordings": { items: [call], next_cursor: null },
      "/v1/recordings/r1": { ...call, share_note: "Strong close. Ask about budget earlier.", shared_by_name: "Kavita" },
      "/v1/recordings/r1/analysis": {
        status: "completed", summary: "A friendly renewal call that ended with a date for the demo.",
        strengths: ["Summarised the customer's needs before pricing"], gaps: [],
        suggestions: [{ text: "Ask who else decides before quoting.", utterance_id: "u7", start_ms: 312_000 }],
      }, // prettier-ignore
    });
    const router = renderAt("/");

    expect(await screen.findByRole("heading", { level: 1, name: /, Rohan$/ })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/progress");
    const tiles = await screen.findByRole("region", { name: "In this period" });
    expect(within(tiles).getByText("Your median sales score")).toBeInTheDocument();
    expect(within(tiles).getByText("Up 0.3 vs prev. 30 days")).toBeInTheDocument();
    expect(within(tiles).queryByText("Audio processed")).not.toBeInTheDocument();

    expect(await screen.findByText("Strong close. Ask about budget earlier.")).toBeInTheDocument();
    expect(screen.getByText("Note from Kavita")).toBeInTheDocument();
    expect(await screen.findByText("Ask who else decides before quoting.")).toBeInTheDocument();
    expect(screen.getByText("at 5:12")).toBeInTheDocument();

    const focus = screen.getByRole("region", { name: "What to work on next" });
    expect(
      within(focus)
        .getAllByRole("listitem")
        .map((li) => li.querySelector("span")?.textContent),
    ).toEqual(["Discovery questions", "Objection handling", "Demo tied to needs"]);
  });

  it("asks a new teacher to upload their first lesson instead of showing empty panels", async () => {
    stubApi({
      "/v1/me": teacher,
      "/v1/overview": { ...emptyOverview(), units: [], processing: [] },
      "/v1/recordings": { items: [], next_cursor: null },
    });
    renderAt("/progress");

    expect(await screen.findByRole("heading", { name: "Upload your first lesson" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "What to work on next" })).not.toBeInTheDocument();
  });
});
