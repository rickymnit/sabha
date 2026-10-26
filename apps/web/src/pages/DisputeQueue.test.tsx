import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/queries";
import { routes } from "../app/routes";
import { ToastProvider } from "../design";
import { StaticSessionProvider } from "../session/providers";
import type { Session } from "../session/session";

const labels = { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                 unit: "Class", manager: "Coordinator" }; // prettier-ignore
const ME = {
  user: { id: "u1", email: "r@x", name: "Rahul Verma", role: "reviewer", title: null, unit_ids: ["unit-6"] },
  tenant: { id: "t", name: "Demo School", profile: "school", labels, enabled_types: ["teaching"],
            units: [{ id: "unit-6", name: "Class 6" }] }, // prettier-ignore
};
const DISPUTE = {
  kind: "dispute", id: "d1", recording_id: "r9", recording_title: "Waves", person_name: "Asha Rao", unit: "Class 6",
  dimension_key: "concept_clarity", dimension_name: "Concept clarity", ai_score: 4, current_score: 4,
  proposed_score: 5, comment: "Both terms were defined and checked.", status: "open", raised_by_me: false,
  evidence: [{ quote: "Chlorophyll leaf ka green pigment hai", start_ms: 34_000 }], created_at: "2026-10-26T05:00:00Z",
}; // prettier-ignore

function stubApi(dispute: Record<string, unknown> = DISPUTE) {
  const fetchMock = vi.fn<(path: string, init?: RequestInit) => Promise<Response>>(async (path, init) => {
    const body = path.startsWith("/v1/me")
      ? ME
      : path.startsWith("/v1/disputes?")
        ? { items: [dispute], next_cursor: null }
        : path.endsWith("/resolve") && init?.method === "POST"
          ? { ...dispute, status: "accepted" }
          : { items: [], next_cursor: null };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAt(path: string) {
  const session: Session = { mode: "dev", token: "t", ready: true, signOut: vi.fn() };
  render(
    <StaticSessionProvider session={session}>
      <ToastProvider>
        <QueryClientProvider client={createQueryClient()}>
          <RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />
        </QueryClientProvider>
      </ToastProvider>
    </StaticSessionProvider>,
  );
}

const resolved = (fetchMock: ReturnType<typeof stubApi>) =>
  fetchMock.mock.calls.filter(([path, init]) => path.endsWith("/resolve") && init?.method === "POST");

afterEach(() => vi.unstubAllGlobals());

describe("disputes on the reviews page", () => {
  it("lists disputed scores with their evidence and counts them in the menu", async () => {
    stubApi();
    renderAt("/reviews?tab=disputes");
    const detail = await screen.findByRole("region", { name: "Waves" });
    expect(within(detail).getByText("Both terms were defined and checked.")).toBeInTheDocument();
    expect(within(detail).getByText("Chlorophyll leaf ka green pigment hai")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disputes (1)" })).toHaveAttribute("aria-pressed", "true");
    const menu = screen.getByRole("navigation", { name: "Main" });
    expect(await within(menu).findByText("1 waiting", { exact: false })).toBeInTheDocument();
  });

  it("accepts with the final score and a note", async () => {
    const fetchMock = stubApi();
    renderAt("/reviews?tab=disputes");
    const detail = await screen.findByRole("region", { name: "Waves" });
    await userEvent.type(within(detail).getByRole("textbox", { name: "Note to the person" }), "The quotes agree.");
    await userEvent.click(within(detail).getByRole("button", { name: "Accept and set score" }));
    await waitFor(() => expect(resolved(fetchMock)).toHaveLength(1));
    expect(resolved(fetchMock)[0]?.[0]).toBe("/v1/disputes/d1/resolve");
    expect(JSON.parse(String(resolved(fetchMock)[0]?.[1]?.body))).toEqual({
      decision: "accepted",
      final_score: 5,
      note: "The quotes agree.",
    });
  });

  it("says someone else decides a dispute you raised", async () => {
    stubApi({ ...DISPUTE, raised_by_me: true });
    renderAt("/reviews?tab=disputes");
    expect(await screen.findByText(/You raised this dispute, so another reviewer/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept and set score" })).toBeNull();
  });
});
