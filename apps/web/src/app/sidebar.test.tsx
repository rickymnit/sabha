import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { affectedQueries } from "../api/live";
import { ToastProvider } from "../design";
import { StaticSessionProvider } from "../session/providers";
import type { Session } from "../session/session";
import { formatHours } from "./format";
import { PlanUsage } from "./PlanUsage";
import { createQueryClient } from "./queries";
import { routes } from "./routes";

function me(role: string) {
  return {
    user: { id: "u-1", email: "p@demo.example", name: "Priya Kapoor", role, title: null, unit_ids: [] },
    tenant: {
      id: "t", name: "Demo School", profile: "school", enabled_types: ["teaching", "reception", "sales"], units: [],
      labels: { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                unit: "Class", manager: "Coordinator" },
    }, // prettier-ignore
  };
}

const USAGE = { plan: "starter", used_hours: 38.44, allowance_hours: 100, state: "ok", message: null,
                resets_at: "2026-10-31T18:30:00Z" }; // prettier-ignore

/** Answers by the longest matching path, so /v1/recordings/counts is not mistaken for the list. */
function stubApi(answers: Record<string, unknown>) {
  const fetchMock = vi.fn(async (path: string) => {
    const key = Object.keys(answers)
      .filter((prefix) => path.startsWith(prefix))
      .sort((a, b) => b.length - a.length)[0];
    if (!key) return new Response(JSON.stringify({ code: "not_found", title: "Not found" }), { status: 404 });
    const answer = answers[key];
    if (answer instanceof Response) return answer;
    return new Response(JSON.stringify(answer), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const session: Session = { mode: "dev", token: "token", ready: true, signInAs: vi.fn(), signOut: vi.fn() };

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <StaticSessionProvider session={session}>
      <ToastProvider>
        <QueryClientProvider client={createQueryClient()}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ToastProvider>
    </StaticSessionProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("the menu's numbers", () => {
  it("shows how many recordings of each type, zero included, and the plan's hours to an owner", async () => {
    stubApi({
      "/v1/me": me("owner"),
      "/v1/recordings/counts": { by_type: { teaching: 128, reception: 46 } },
      "/v1/recordings": { items: [], next_cursor: null },
      "/v1/usage": USAGE,
    });
    renderAt("/recordings");
    const menu = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(menu).findByRole("link", { name: "Teaching, 128" })).toBeInTheDocument();
    expect(within(menu).getByRole("link", { name: "Reception, 46" })).toBeInTheDocument();
    expect(within(menu).getByRole("link", { name: "Sales, 0" })).toBeInTheDocument();
    const plan = await within(menu).findByRole("region", { name: "Plan usage" });
    expect(within(plan).getByText("Audio this month")).toBeInTheDocument();
    expect(within(plan).getByText("38.4 of 100 audio hours used")).toBeInTheDocument();
    expect(within(plan).getByRole("progressbar")).toHaveAttribute("aria-valuetext", "38.4 of 100 audio hours used");
  });

  it("never asks for or shows the plan to staff", async () => {
    const fetchMock = stubApi({
      "/v1/me": me("staff"),
      "/v1/recordings/counts": { by_type: { teaching: 3 } },
      "/v1/recordings": { items: [], next_cursor: null },
    });
    renderAt("/recordings");
    const menu = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(menu).findByRole("link", { name: "Teaching, 3" })).toBeInTheDocument();
    expect(within(menu).queryByRole("region", { name: "Plan usage" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([path]) => path.startsWith("/v1/usage"))).toBe(false);
  });

  it("keeps the page working when the numbers cannot be loaded", async () => {
    const down = () => new Response(JSON.stringify({ code: "not_ready", title: "Not ready" }), { status: 503 });
    stubApi({
      "/v1/me": me("owner"),
      "/v1/recordings/counts": down(),
      "/v1/recordings": { items: [], next_cursor: null },
      "/v1/usage": down(),
    });
    renderAt("/recordings");
    const menu = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(menu).findByRole("link", { name: "Teaching" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(within(menu).queryByRole("region", { name: "Plan usage" })).not.toBeInTheDocument();
  });
});

describe("the plan block", () => {
  const renderBlock = (overrides: Record<string, unknown>) =>
    render(<PlanUsage usage={{ ...USAGE, ...overrides } as typeof USAGE & { state: "ok" }} />);

  it("shows hours used without a limit until Sabha sets an allowance", () => {
    renderBlock({ plan: "pilot", used_hours: 3.2, allowance_hours: null, state: null });
    expect(screen.getByText("3.2 h")).toBeInTheDocument();
    expect(screen.getByText("3.2 audio hours this month")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("warns near the limit and says when uploads pause", () => {
    const { unmount } = renderBlock({
      used_hours: 85,
      state: "warning",
      message: "85 of this month's 100 audio hours are used.",
    });
    expect(screen.getByText("85 of this month's 100 audio hours are used.")).toBeInTheDocument();
    unmount();
    renderBlock({ used_hours: 104, state: "blocked", message: "New uploads are paused until 1 November 2026." });
    expect(screen.getByText("New uploads are paused until 1 November 2026.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });

  it("writes hours plainly", () => {
    expect([formatHours(38.44), formatHours(2), formatHours(0.04), formatHours(1.96)]).toEqual(["38.4", "2", "0", "2"]);
  });
});

describe("live status", () => {
  it("refreshes the counts with the lists, and the hours once a recording is measured", () => {
    const at = (status: string) => affectedQueries({ type: "recording.status", recording_id: "r", status } as never);
    expect(at("TRANSCRIBING")).toContainEqual(["recordings"]); // ["recordings", "counts", token] is under it
    expect(at("DIARIZING")).toContainEqual(["usage"]);
    expect(at("TRANSCRIBING")).not.toContainEqual(["usage"]);
  });
});
