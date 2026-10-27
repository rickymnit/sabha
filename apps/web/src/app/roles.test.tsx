// What each role sees (P6.8). The API decides what data anyone may read (tests/security/permissions.yaml); these
// tests check the app around it: each role's menu, what a staff member meets on a colleague's report link, and the
// note after a session ends on its own.

import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { ToastProvider } from "../design";
import { StaticSessionProvider } from "../session/providers";
import type { Session } from "../session/session";
import { ApiErrors } from "./App";
import { API_ERROR_EVENT, createQueryClient } from "./queries";
import { routes } from "./routes";

function me(role: string) {
  return {
    user: { id: "u-1", email: "p@demo.example", name: "Priya Kapoor", role, title: null, unit_ids: ["unit-6"] },
    tenant: { id: "t", name: "Demo School", profile: "school", enabled_types: ["teaching"],
              units: [{ id: "unit-6", name: "Class 6" }],
              labels: { person: "Teacher", person_plural: "Teachers", recording: "Lesson",
                        recording_plural: "Lessons", unit: "Class", manager: "Coordinator" } }, // prettier-ignore
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubApi(answers: Record<string, Response | unknown>) {
  const fetchMock = vi.fn(async (path: string) => {
    const key = Object.keys(answers)
      .filter((prefix) => path.startsWith(prefix))
      .sort((a, b) => b.length - a.length)[0];
    if (!key) return json({ code: "not_found", title: "Not found" }, 404);
    const answer = answers[key];
    return answer instanceof Response ? answer.clone() : json(answer);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const session: Session = { mode: "dev", token: "token", ready: true, signInAs: vi.fn(), signOut: vi.fn() };

function renderAt(path: string, withSession: Session = session) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <StaticSessionProvider session={withSession}>
      <ToastProvider>
        <ApiErrors />
        <QueryClientProvider client={createQueryClient()}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ToastProvider>
    </StaticSessionProvider>,
  );
  return router;
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

const EMPTY = { items: [], next_cursor: null };
const MENUS: [string, string[]][] = [
  ["owner", ["Overview", "Lessons", "Reviews", "Teachers", "Rubrics", "Upload", "Activity", "Settings"]],
  ["admin", ["Overview", "Lessons", "Reviews", "Teachers", "Rubrics", "Upload", "Activity", "Settings"]],
  ["manager", ["Overview", "Lessons", "Reviews", "Teachers", "Rubrics", "Upload"]],
  ["reviewer", ["Overview", "Lessons", "Reviews", "Teachers", "Rubrics", "Upload"]],
  ["staff", ["Lessons", "Rubrics", "Upload"]],
];

describe("each role's menu", () => {
  it.each(MENUS)("%s sees only their pages", async (role, expected) => {
    stubApi({ "/v1/me": me(role), "/v1/recordings": EMPTY, "/v1/reviews": EMPTY, "/v1/disputes": EMPTY });
    renderAt("/recordings");
    const menu = await screen.findByRole("navigation", { name: "Main" });
    await within(menu).findByText("Priya Kapoor");
    const pages = within(menu)
      .getAllByRole("link")
      .map((a) => a.textContent)
      .filter((text) => text !== "Teaching"); // the conversation-type links
    expect(pages).toEqual(expected);
  });
});

describe("a colleague's report", () => {
  it("is not found for staff, with a way back and nothing about whose it is", async () => {
    const hidden = json({ code: "not_found", title: "Not found", status: 404,
                          detail: "This recording does not exist or you cannot see it." }, 404); // prettier-ignore
    stubApi({ "/v1/me": me("staff"), "/v1/recordings/r-ravi": hidden, "/v1/recordings": EMPTY });
    renderAt("/recordings/r-ravi");
    expect(await screen.findByRole("heading", { name: "We couldn't find this lesson" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to lessons" })).toBeInTheDocument();
    expect(screen.queryByText(/does not exist or you cannot see it/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("offers to try again when the report fails to load, with the reference to quote", async () => {
    const down = json({ code: "not_ready", title: "Not ready", status: 503, request_id: "req-42" }, 503);
    stubApi({ "/v1/me": me("owner"), "/v1/recordings/r-1": down, "/v1/recordings": EMPTY });
    renderAt("/recordings/r-1");
    expect(
      await screen.findByRole("heading", { name: "We couldn't load this lesson" }, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/quote reference req-42/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("a session that ends on its own", () => {
  it("signs out on a 401 and the sign-in page says why", async () => {
    const signOut = vi.fn();
    stubApi({ "/dev-idp/users": [] });
    renderAt("/login", { ...session, token: undefined, signOut });
    await screen.findByRole("heading", { name: "Welcome" });
    expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument();

    window.dispatchEvent(
      new CustomEvent(API_ERROR_EVENT, { detail: new ApiError(401, "unauthorized", "Not signed in", "") }),
    );
    expect(signOut).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();

    stubApi({ "/dev-idp/users": [] });
    renderAt("/login", { ...session, token: undefined });
    expect(
      await screen.findAllByText("Your session ended. Please sign in again to carry on where you were."),
    ).toHaveLength(1);
  });

  it("does not show the note after an ordinary sign-out", async () => {
    stubApi({ "/dev-idp/users": [] });
    renderAt("/login", { ...session, token: undefined });
    await screen.findByRole("heading", { name: "Welcome" });
    expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument();
  });
});

describe("pages for some roles only", () => {
  it.each(["/overview", "/people", "/reviews", "/reviews/r9"])(
    "send a teacher who types %s to their lessons",
    async (path) => {
      stubApi({ "/v1/me": me("staff"), "/v1/recordings": EMPTY });
      const router = renderAt(path);
      expect(await screen.findByRole("heading", { level: 1, name: "Lessons" })).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/recordings");
    },
  );

  it("still open for a coordinator", async () => {
    stubApi({ "/v1/me": me("manager"), "/v1/recordings": EMPTY, "/v1/reviews": EMPTY, "/v1/disputes": EMPTY,
              "/v1/people/summary": [] }); // prettier-ignore
    const router = renderAt("/people");
    expect(await screen.findByRole("heading", { level: 1, name: "Teachers" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/people");
  });
});
