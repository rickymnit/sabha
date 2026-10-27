import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/queries";
import { routes } from "../app/routes";
import { ToastProvider } from "../design";
import { StaticSessionProvider } from "../session/providers";
import type { Session } from "../session/session";

const ME = {
  user: { id: "u-asha", email: "a@demo.example", name: "Asha Rao", role: "staff", title: null, unit_ids: [] },
  tenant: { id: "t", name: "Demo School", profile: "school", enabled_types: ["teaching", "reception"], units: [],
            labels: { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                      unit: "Class", manager: "Coordinator" } }, // prettier-ignore
};

const LIST = {
  items: [
    { type: "teaching", current_id: "teaching.school.v0.1", dimension_count: 2,
      versions: [{ id: "teaching.school.v0.1", version: "0.1", in_use: true }] }, // prettier-ignore
    { type: "reception", current_id: "reception.school.v0.2", dimension_count: 1,
      versions: [{ id: "reception.school.v0.2", version: "0.2", in_use: true },
                 { id: "reception.school.v0.1", version: "0.1", in_use: false }] }, // prettier-ignore
  ],
};

const scale = (prefix: string) =>
  [1, 2, 3, 4, 5].map((level) => ({
    level,
    description: `${prefix} level ${level}`,
    example: level === 1 ? `${prefix} example one` : null,
  }));

const TEACHING = {
  id: "teaching.school.v0.1", type: "teaching", version: "0.1", in_use: true,
  dimensions: [
    { key: "concept_clarity", name: "Concept clarity", weight: 0.6, definition: "States the main idea.",
      min_quotes: 2, not_applicable_when: null, scale: scale("Clarity") },
    { key: "pacing", name: "Pacing", weight: 0.4, definition: "Moves at a steady pace.", min_quotes: 1,
      not_applicable_when: "The recording is under five minutes.", scale: scale("Pacing") },
  ],
  versions: [{ id: "teaching.school.v0.1", version: "0.1", in_use: true }],
  previous_id: null, changes: [],
}; // prettier-ignore

const RECEPTION_V2 = {
  id: "reception.school.v0.2", type: "reception", version: "0.2", in_use: true,
  dimensions: [{ key: "greeting", name: "Greeting", weight: 1, definition: "Greets the caller.", min_quotes: 1,
                 not_applicable_when: null, scale: scale("Greeting") }],
  versions: LIST.items[1]!.versions, previous_id: "reception.school.v0.1",
  changes: [
    { dimension: "greeting", item: "weight", old: "0.5", new: "1" },
    { dimension: "greeting", item: "anchors[2]", old: "a", new: "b" },
    { dimension: "hold", item: "dimension removed", old: null, new: null },
  ],
}; // prettier-ignore

function stubApi(answers: Record<string, unknown>) {
  const fetchMock = vi.fn(async (path: string) => {
    const key = Object.keys(answers)
      .filter((prefix) => path.startsWith(prefix))
      .sort((a, b) => b.length - a.length)[0];
    if (!key || answers[key] === null)
      return new Response(JSON.stringify({ code: "not_found", title: "Not found" }), { status: 404 });
    return new Response(JSON.stringify(answers[key]), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const session: Session = { mode: "dev", token: "token", ready: true, signInAs: vi.fn(), signOut: vi.fn() };

function renderAt(path: string) {
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

const API = {
  "/v1/me": ME,
  "/v1/rubrics/teaching.school.v0.1": TEACHING,
  "/v1/rubrics/reception.school.v0.2": RECEPTION_V2,
  "/v1/rubrics": LIST,
  "/v1/recordings": { items: [], next_cursor: null },
};

afterEach(() => vi.unstubAllGlobals());

describe("the rubrics page", () => {
  it("is in a teacher's menu and opens the first rubric", async () => {
    stubApi(API);
    const router = renderAt("/rubrics");
    expect(await screen.findByRole("heading", { level: 1, name: "Teaching rubric" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/rubrics/teaching.school.v0.1");
    const menu = screen.getByRole("navigation", { name: "Main" });
    expect(within(menu).getByRole("link", { name: "Rubrics" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Version 0.1, in use. Every teaching recording is scored with it.")).toBeInTheDocument();
  });

  it("lists dimensions with weights and quotes, and shows the chosen one's scale with examples", async () => {
    stubApi(API);
    renderAt("/rubrics/teaching.school.v0.1");
    const table = await screen.findByRole("table", { name: "Dimensions" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map((r) =>
        within(r)
          .getAllByRole("cell")
          .map((c) => c.textContent),
      ),
    ).toEqual([
      ["Concept clarity", "60%", "2"],
      ["Pacing", "40%", "1"],
    ]);
    expect(screen.getByRole("heading", { name: "Concept clarity" })).toBeInTheDocument();
    expect(screen.getByText("Clarity level 5")).toBeInTheDocument();
    expect(screen.getByText("Clarity example one")).toBeInTheDocument();

    await userEvent.click(within(table).getByRole("button", { name: "Pacing" }));
    expect(screen.getByRole("heading", { name: "Pacing" })).toBeInTheDocument();
    expect(screen.getByText("The recording is under five minutes.")).toBeInTheDocument();
    expect(screen.queryByText("Clarity level 5")).not.toBeInTheDocument();
  });

  it("shows versions and what changed, in plain words", async () => {
    stubApi(API);
    renderAt("/rubrics/reception.school.v0.2");
    const changes = await screen.findByRole("region", { name: "Changes from v0.1" });
    expect(
      within(changes)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["Greeting: weight 50% to 100%", "Greeting: level 2 description changed", "Hold: removed"]);
    const history = screen.getByRole("region", { name: "Version history" });
    expect(within(history).getByRole("link", { name: /v0\.2/ })).toHaveAttribute("aria-current", "page");
    expect(within(history).getByText("In use")).toBeInTheDocument();
  });

  it("never shows agreement numbers or an edit button", async () => {
    stubApi(API);
    renderAt("/rubrics/teaching.school.v0.1");
    await screen.findByRole("table", { name: "Dimensions" });
    expect(screen.queryByText(/agreement/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /publish|edit|add dimension/i })).not.toBeInTheDocument();
  });

  it("explains a rubric the organisation does not use", async () => {
    stubApi({ ...API, "/v1/rubrics/sales.company.v0.2": null });
    renderAt("/rubrics/sales.company.v0.2");
    expect(await screen.findByText("This rubric is not used by your organisation")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "All rubrics" })).toBeInTheDocument();
  });
});
