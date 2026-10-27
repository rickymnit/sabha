import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe as group, expect, it, vi } from "vitest";

import type { AuditEntryItem } from "../../api/types";
import { createQueryClient } from "../../app/queries";
import { routes } from "../../app/routes";
import { ToastProvider } from "../../design";
import { StaticSessionProvider } from "../../session/providers";
import type { Session } from "../../session/session";
import { describe } from "./describe";

const LABELS = { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                 unit: "Class", manager: "Coordinator" }; // prettier-ignore

function me(role: string) {
  return {
    user: { id: "u-1", email: "p@demo.example", name: "Priya Sharma", role, title: null, unit_ids: [] },
    tenant: { id: "t", name: "Demo School", profile: "school", labels: LABELS, enabled_types: ["teaching"],
              units: [] }, // prettier-ignore
  };
}

function entry(overrides: Partial<AuditEntryItem> = {}): AuditEntryItem {
  return {
    id: `a-${Math.random()}`,
    at: "2026-10-27T05:00:00Z",
    action: "recording.play",
    actor: { id: "u-neha", name: "Neha Joshi", role: "admin" },
    target: { type: "recording", id: "r-1", label: "Fractions, Class 7B" },
    meta: {},
    ...overrides,
  };
}

const sentence = (e: AuditEntryItem) => {
  const d = describe(e, LABELS);
  return `${[d.text, d.target].filter(Boolean).join(" ")}${d.after ?? ""}`;
};

group("entries in plain words", () => {
  it("names what was done to which recording, in the tenant's words", () => {
    expect(describe(entry(), LABELS)).toEqual({
      text: "played the audio of",
      target: "Fractions, Class 7B",
      href: "/recordings/r-1",
    });
    expect(sentence(entry({ action: "analysis.view" }))).toBe("opened the report for Fractions, Class 7B");
    expect(
      sentence(entry({ action: "dispute.create", target: { type: "dispute", id: "d", label: "Fractions" } })),
    ).toBe("disputed a score on Fractions");
    expect(sentence(entry({ target: { type: "recording", id: "r-x", label: null } }))).toBe(
      "played the audio of a lesson that no longer exists",
    );
  });

  it("spells out settings changes from before and after", () => {
    const meta = {
      before: { labels: { person: "Teacher" }, name: "Demo School" },
      after: { labels: { person: "Educator" }, name: "Demo Public School", enabled_types: ["teaching", "reception"] },
    };
    expect(describe(entry({ action: "settings.update", target: { type: "tenant", id: "t", label: null }, meta }), LABELS))
      .toEqual({
        text: "renamed the organisation to “Demo Public School”; changed the word “Teacher” to “Educator”; set the conversation types to Teaching, Reception",
        target: null,
      }); // prettier-ignore
  });

  it("says whom someone invited and as what, with the right article", () => {
    const invite = (role: string) =>
      sentence(
        entry({ action: "user.invite", target: { type: "user", id: "u-9", label: "Ravi Kumar" }, meta: { role } }),
      );
    expect(invite("staff")).toBe("invited Ravi Kumar as a teacher");
    expect(invite("admin")).toBe("invited Ravi Kumar as an administrator");
  });

  it("still shows an action it does not know", () => {
    expect(sentence(entry({ action: "export.create", target: { type: "export", id: "x", label: null } }))).toBe(
      "export create",
    );
  });
});

function stubApi(role: string, items: AuditEntryItem[] = [], nextCursor: string | null = null) {
  const fetchMock = vi.fn(async (path: string) => {
    const body = path.startsWith("/v1/me")
      ? me(role)
      : path.startsWith("/v1/audit")
        ? { items, next_cursor: path.includes("cursor=") ? null : nextCursor }
        : { items: [], next_cursor: null };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
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

const auditCalls = (fetchMock: ReturnType<typeof stubApi>) =>
  fetchMock.mock.calls.map(([path]) => path).filter((path) => path.startsWith("/v1/audit"));

afterEach(() => vi.unstubAllGlobals());

group("the activity page", () => {
  it("lists who did what for an owner, with the recording linked", async () => {
    stubApi("owner", [
      entry(),
      entry({ action: "analysis.view", actor: { id: "u-gone", name: null, role: "manager" } }),
    ]);
    const router = renderAt("/activity");
    const table = await screen.findByRole("table", { name: "Activity" });
    const [first, second] = within(table).getAllByRole("row").slice(1);
    expect(first).toHaveTextContent("Neha Joshi");
    expect(first).toHaveTextContent("Administrator");
    expect(first).toHaveTextContent("Played the audio of Fractions, Class 7B");
    expect(second).toHaveTextContent("Someone no longer here");
    await userEvent.click(within(first!).getByRole("link", { name: "Fractions, Class 7B" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/recordings/r-1"));
  });

  it("filters by what, when and who", async () => {
    const fetchMock = stubApi("admin", [entry()]);
    renderAt("/activity");
    await screen.findByRole("table", { name: "Activity" });
    expect(auditCalls(fetchMock).at(-1)).toMatch(/from=/); // the last 30 days by default

    await userEvent.selectOptions(screen.getByLabelText("What"), "Played audio");
    await waitFor(() => expect(auditCalls(fetchMock).at(-1)).toContain("action=recording.play"));
    await userEvent.selectOptions(screen.getByLabelText("When"), "All time");
    await waitFor(() => expect(auditCalls(fetchMock).at(-1)).not.toMatch(/from=/));
    await userEvent.click(screen.getByRole("button", { name: /Neha Joshi/ }));
    await waitFor(() => expect(auditCalls(fetchMock).at(-1)).toContain("actor_user_id=u-neha"));
    await userEvent.click(screen.getByRole("button", { name: "Show everyone, not only Neha Joshi" }));
    await waitFor(() => expect(auditCalls(fetchMock).at(-1)).not.toContain("actor_user_id"));
  });

  it("shows older entries on request", async () => {
    const fetchMock = stubApi("owner", [entry()], "next-page");
    renderAt("/activity");
    await userEvent.click(await screen.findByRole("button", { name: "Show older" }));
    await waitFor(() => expect(auditCalls(fetchMock).at(-1)).toContain("cursor=next-page"));
  });

  it("says when nothing matches and offers to clear the filters", async () => {
    stubApi("owner", []);
    renderAt("/activity");
    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("What"), "Invited people");
    expect(await screen.findByText("Nothing matches these filters")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
  });

  it.each(["manager", "reviewer", "staff"])("is not for a %s", async (role) => {
    const fetchMock = stubApi(role);
    const router = renderAt("/activity");
    await waitFor(() => expect(router.state.location.pathname).not.toBe("/activity"));
    expect(auditCalls(fetchMock)).toEqual([]);
  });
});
