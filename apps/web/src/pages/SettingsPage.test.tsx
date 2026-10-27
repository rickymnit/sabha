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

const LABELS = { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                 unit: "Class", manager: "Coordinator" }; // prettier-ignore

function me(role: string, labels = LABELS) {
  return {
    user: { id: "u-1", email: "p@demo.example", name: "Priya Kapoor", role, title: null, unit_ids: [] },
    tenant: { id: "t", name: "Demo School", profile: "school", labels, enabled_types: ["teaching", "reception"],
              units: [] }, // prettier-ignore
  };
}

function settings(overrides: Record<string, unknown> = {}) {
  return {
    name: "Demo School",
    profile: "school",
    plan: "pilot",
    labels: LABELS,
    enabled_types: ["teaching", "reception"],
    types: [
      { type: "teaching", enabled: true, available: true },
      { type: "counselling", enabled: false, available: false },
      { type: "reception", enabled: true, available: true },
      { type: "meeting", enabled: false, available: false },
      { type: "sales", enabled: false, available: false },
    ],
    max_types: 5,
    retention_days: 90,
    ...overrides,
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** A small fake API: GET /v1/me and /v1/settings, PATCH /v1/settings answered by `onPatch`. */
function stubApi(role: string, onPatch?: (body: Record<string, unknown>) => Response) {
  let current = me(role);
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith("/v1/me")) return json(current);
    if (path.startsWith("/v1/settings") && init?.method === "PATCH") {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      const answer = onPatch?.(body) ?? json(settings());
      if (answer.ok) {
        const saved = (await answer.clone().json()) as { labels: typeof LABELS };
        current = me(role, saved.labels);
      }
      return answer;
    }
    if (path.startsWith("/v1/settings")) return json(settings());
    if (path.startsWith("/v1/")) return json({ items: [], next_cursor: null });
    return json({ code: "not_found", title: "Not found" }, 404);
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

function patches(fetchMock: ReturnType<typeof stubApi>) {
  return fetchMock.mock.calls
    .filter(([, init]) => init?.method === "PATCH")
    .map(([, init]) => JSON.parse(String(init?.body)) as unknown);
}

afterEach(() => vi.unstubAllGlobals());

describe("the settings page", () => {
  it("is in an owner's menu but not a teacher's", async () => {
    stubApi("owner");
    renderAt("/recordings");
    const menu = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(menu).findByRole("link", { name: "Settings" })).toBeInTheDocument();
    vi.unstubAllGlobals();

    stubApi("staff");
    renderAt("/settings");
    expect(await screen.findByText("Only owners and administrators can change settings")).toBeInTheDocument();
    const menus = await screen.findAllByRole("navigation", { name: "Main" });
    expect(within(menus.at(-1) as HTMLElement).queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("renames a word, sends only what changed, and the menu uses the new word at once", async () => {
    const fetchMock = stubApi("admin", (body) => json(settings({ labels: { ...LABELS, ...(body.labels as object) } })));
    renderAt("/settings");
    const field = await screen.findByLabelText("Several of them");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await userEvent.clear(field);
    await userEvent.type(field, "  Educators ");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await screen.findByText("Settings saved");
    expect(patches(fetchMock)).toEqual([{ labels: { person_plural: "Educators" } }]);
    const menu = screen.getByRole("navigation", { name: "Main" });
    await waitFor(() => expect(within(menu).getByRole("link", { name: "Educators" })).toBeInTheDocument());
    expect(screen.getByText("All changes saved.")).toBeInTheDocument();
  });

  it("refuses an empty word without calling the API", async () => {
    const fetchMock = stubApi("owner");
    renderAt("/settings");
    await userEvent.clear(await screen.findByLabelText("A recording"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("This cannot be empty.")).toBeInTheDocument();
    expect(patches(fetchMock)).toEqual([]);
  });

  it("explains types the organisation cannot switch on and keeps one on", async () => {
    const fetchMock = stubApi("owner");
    renderAt("/settings");
    const meetings = await screen.findByRole("checkbox", { name: "Meetings" });
    expect(meetings).toBeDisabled();
    expect(screen.getAllByText(/Not set up for your organisation yet/)).toHaveLength(3);

    await userEvent.click(screen.getByRole("checkbox", { name: "Teaching" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Reception" }));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Keep at least one conversation type on.")).toHaveAttribute("role", "alert");
    expect(patches(fetchMock)).toEqual([]);
  });

  it("shows the plan limit the API answers with next to the types", async () => {
    stubApi(
      "owner",
      () =>
      json({ code: "plan_limit", title: "Plan limit reached", status: 422,
             detail: "Your plan covers 2 conversation types at a time." }, 422), // prettier-ignore
    );
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Teaching" }));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Your plan covers 2 conversation types at a time.")).toHaveAttribute(
      "role",
      "alert",
    );
  });
});

// CLAUDE.md: UI words come from the tenant's labels; never hard-code "Teacher" or "Lesson". Pages and features are
// scanned for those words in string literals and JSX text (comments are ignored). Demo pages (dev/, spike/), sample
// data (mock.ts) and tests are exempt; the setup design's type descriptions say "Lessons, lectures" on purpose.
const SOURCES = import.meta.glob(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}", "!../dev/**", "!../spike/**",
                                  "!../**/mock.ts", "!../test/**"], { query: "?raw", import: "default", eager: true }); // prettier-ignore
const NOUNS = /\b(Teachers?|Lessons?|Principal)\b/;
const ALLOWED = [/Lessons, lectures and training/];

function uiText(source: string): string[] {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  const strings = code.match(/"[^"\n]*"|'[^'\n]*'|`[^`]*`|>[^<>{}]+</g) ?? [];
  return strings.filter((s) => NOUNS.test(s) && !ALLOWED.some((ok) => ok.test(s)));
}

describe("UI words", () => {
  it("never hard-codes the tenant's nouns", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(20);
    const offenders = Object.entries(SOURCES).flatMap(([file, source]) =>
      uiText(source as string).map((text) => `${file}: ${text}`),
    );
    expect(offenders).toEqual([]);
  });
});
