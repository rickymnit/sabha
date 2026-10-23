import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../design";
import { reportRecording, roleLabels } from "../pages/recordingView";
import { DevSessionProvider, StaticSessionProvider } from "../session/providers";
import { authMode, DEV_TOKEN_KEY, type Session } from "../session/session";
import { formatDuration, formatWhen, roleTitle, statusChip, viewerRole } from "./format";
import { createQueryClient } from "./queries";
import { routes } from "./routes";

const ME = {
  user: { id: "u-asha", email: "asha@demo.example", name: "Asha Rao", role: "staff", title: "Teacher, Class 6",
          unit_ids: ["unit-6"] }, // prettier-ignore
  tenant: {
    id: "demo-school",
    name: "Demo School",
    profile: "school",
    labels: { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
              unit: "Class", manager: "Coordinator" }, // prettier-ignore
    enabled_types: ["teaching", "reception"],
    units: [{ id: "unit-6", name: "Class 6" }],
  },
};
const PAGE = {
  items: [
    { id: "r1", title: "Fractions", type: "teaching", status: "COMPLETED", status_reason: null, status_note: null,
      person: { id: "p-asha", name: "Asha" },
      unit_id: "unit-6", file_name: "Fractions.mp3", duration_ms: 2_700_000, created_at: "2026-10-22T04:30:00Z",
      status_changed_at: null, completed_at: null, overall_score: 3.6 }, // prettier-ignore
    { id: "r2", title: "Decimals", type: "teaching", status: "TRANSCRIBING", status_reason: null, status_note: null,
      person: { id: "p-asha", name: "Asha" },
      unit_id: "unit-6", file_name: "Decimals.mp3", duration_ms: null, created_at: "2026-10-22T05:00:00Z",
      status_changed_at: null, completed_at: null, overall_score: null }, // prettier-ignore
    { id: "r3", title: "Silent test", type: "reception", status: "FAILED", status_reason: "no_speech",
      status_note: "No speech was found in the recording.", person: { id: "p-asha", name: "Asha" }, unit_id: "unit-6",
      file_name: "Silent test.wav", duration_ms: 60_000, created_at: "2026-10-21T05:00:00Z", status_changed_at: null,
      completed_at: null, overall_score: null }, // prettier-ignore
  ],
  next_cursor: null,
};

function stubApi(answers: Record<string, unknown>) {
  const fetchMock = vi.fn<(path: string, init?: RequestInit) => Promise<Response>>(async (path) => {
    const key = Object.keys(answers).find((prefix) => path.startsWith(prefix));
    if (!key) return new Response(JSON.stringify({ code: "not_found", title: "Not found" }), { status: 404 });
    return new Response(JSON.stringify(answers[key]), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAt(path: string, session: Session) {
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

const signedOut: Session = { mode: "dev", token: undefined, ready: true, signInAs: vi.fn(), signOut: vi.fn() };
const signedIn: Session = { ...signedOut, token: "token-asha" };

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("the app shell", () => {
  it("sends signed-out people to the dev sign-in, which lists the seeded people", async () => {
    stubApi({ "/dev-idp/users": [{ subject: "dev-asha", name: "Asha Rao", title: "Teacher, Class 6", email: "a@x",
                                   role: "staff", tenant_id: "demo-school", tenant_name: "Demo School" }] }); // prettier-ignore
    renderAt("/recordings", signedOut);
    expect(await screen.findByRole("heading", { name: "Welcome" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Sign in as Asha Rao" })).toBeInTheDocument();
    expect(screen.getByText("Teacher, Class 6")).toBeInTheDocument();
    expect(screen.queryByText(/local development|APP_ENV/i)).not.toBeInTheDocument();
  });

  it("shows the list in the tenant's own words, with statuses and scores", async () => {
    const fetchMock = stubApi({ "/v1/me": ME, "/v1/recordings": PAGE });
    renderAt("/recordings", signedIn);
    expect(await screen.findByRole("heading", { name: "Lessons" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Fractions" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Lesson" })).toBeInTheDocument();
    expect(screen.getAllByText("Asha, Class 6")).toHaveLength(3); // who and where, under each title
    expect(screen.getByText("Analysed")).toBeInTheDocument();
    expect(screen.getByText("Transcribing")).toBeInTheDocument();
    expect(screen.getByText("No speech was found in the recording.")).toBeInTheDocument(); // why it stopped
    expect(screen.queryByText(/lecture|class session/i)).not.toBeInTheDocument();
    const auth = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Record<string, string>;
    expect(auth.Authorization).toBe("Bearer token-asha");
  });
});

describe("the list's filters", () => {
  it("searches titles and filters by type", async () => {
    const fetchMock = stubApi({ "/v1/me": ME, "/v1/recordings": PAGE });
    renderAt("/recordings", signedIn);
    await screen.findByRole("link", { name: "Fractions" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search lessons" }), "deci");
    expect(screen.getByRole("link", { name: "Decimals" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Fractions" })).toBeNull();
    await userEvent.clear(screen.getByRole("searchbox", { name: "Search lessons" }));
    await userEvent.click(screen.getByRole("button", { name: "Reception" }));
    // The type is narrowed by the API (so it holds across pages), not by hiding loaded rows.
    await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => path.includes("type=reception"))).toBe(true));
  });

  it("offers to clear filters that match nothing", async () => {
    stubApi({ "/v1/me": ME, "/v1/recordings": PAGE });
    renderAt("/recordings", signedIn);
    await userEvent.type(await screen.findByRole("searchbox", { name: "Search lessons" }), "zzz");
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("link", { name: "Fractions" })).toBeInTheDocument();
  });

  it("invites the first upload when there is nothing yet", async () => {
    stubApi({ "/v1/me": ME, "/v1/recordings": { items: [], next_cursor: null } });
    renderAt("/recordings", signedIn);
    expect(await screen.findByRole("heading", { name: "No lessons yet" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Upload" }).length).toBeGreaterThan(0);
  });
});

describe("the menu", () => {
  it("lists only finished pages and shows who is signed in", async () => {
    stubApi({ "/v1/me": ME, "/v1/recordings": PAGE });
    renderAt("/recordings", signedIn);
    const menu = await screen.findByRole("navigation", { name: "Main" });
    await within(menu).findByText("Asha Rao");
    const links = within(menu)
      .getAllByRole("link")
      .map((a) => a.textContent);
    expect(links).toEqual(["Lessons", "Upload", "Teaching", "Reception"]);
    expect(within(menu).getByText("Teacher, Class 6")).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("answers an unknown address with a way back, not a placeholder", async () => {
    stubApi({ "/v1/me": ME, "/v1/recordings": PAGE });
    renderAt("/rubrics", signedIn);
    expect(await screen.findByRole("heading", { name: "We couldn't find that page" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to lessons" })).toBeInTheDocument();
    expect(screen.queryByText(/later step of the build/i)).toBeNull();
  });
});

describe("the people page", () => {
  const MANAGER = { ...ME, user: { ...ME.user, name: "Meena Iyer", role: "manager", title: "Coordinator, Class 6" } };
  const SUMMARY = [
    { id: "p-asha", name: "Asha Rao", unit_id: "unit-6", analysed: 3, latest_score: 3.4, recent_scores: [2.5, 3.0, 3.4],
      last_analysed_at: "2026-10-22T05:50:00Z" }, // prettier-ignore
    { id: "p-new", name: "New Teacher", unit_id: "unit-6", analysed: 0, latest_score: null, recent_scores: [],
      last_analysed_at: null }, // prettier-ignore
  ];

  it("is in a manager's menu but not a teacher's", async () => {
    stubApi({ "/v1/me": MANAGER, "/v1/recordings": PAGE });
    renderAt("/recordings", signedIn);
    const menu = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(menu).findByRole("link", { name: "Teachers" })).toBeInTheDocument();
  });

  it("lists each person with real counts, latest score and trend, and opens their lessons", async () => {
    const fetchMock = stubApi({ "/v1/me": MANAGER, "/v1/people/summary": SUMMARY, "/v1/recordings": PAGE });
    renderAt("/people", signedIn);
    expect(await screen.findByRole("heading", { name: "Teachers" })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Last 3 lessons: 2.5 to 3.4, latest 3.4" })).toBeInTheDocument();
    expect(screen.getByText("3.4")).toBeInTheDocument();
    expect(screen.getByText("No scores yet")).toBeInTheDocument(); // nothing invented for someone new
    await userEvent.click(screen.getByRole("link", { name: "Asha Rao" }));
    expect(await screen.findByRole("button", { name: "Show everyone" })).toBeInTheDocument();
    const listCall = fetchMock.mock.calls.map(([path]) => path).find((path) => path.includes("person_id="));
    expect(listCall).toContain("person_id=p-asha"); // the API narrows the list, so it holds across pages
  });
});

describe("the dev session", () => {
  it("keeps the token for the tab after signing in", async () => {
    stubApi({ "/dev-idp/token": { access_token: "tok-1" } });
    let captured: Session | undefined;
    const { useSession } = await import("../session/session");
    function Probe() {
      captured = useSession();
      return null;
    }
    render(
      <DevSessionProvider>
        <Probe />
      </DevSessionProvider>,
    );
    await captured?.signInAs?.("dev-asha");
    await waitFor(() => expect(captured?.token).toBe("tok-1"));
    expect(sessionStorage.getItem(DEV_TOKEN_KEY)).toBe("tok-1");
    captured?.signOut();
    await waitFor(() => expect(captured?.token).toBeUndefined());
  });

  it("is chosen only when VITE_AUTH_MODE says dev", () => {
    expect(authMode({ VITE_AUTH_MODE: "dev" })).toBe("dev");
    expect(authMode({})).toBe("oidc");
  });
});

describe("helpers", () => {
  it("maps statuses, durations and viewer roles", () => {
    expect(statusChip("NEEDS_REVIEW")).toEqual({ chip: "needs-review", text: "Needs review" });
    expect(statusChip("DIARIZING").text).toBe("Finding speakers");
    expect(formatDuration(2_700_000)).toBe("45 min");
    expect(formatDuration(3_900_000)).toBe("1 h 05 min");
    expect(viewerRole("reviewer")).toBe("manager");
  });

  it("says when in plain words, in India time", () => {
    const now = new Date("2026-10-22T10:00:00Z"); // 15:30 in Kolkata
    expect(formatWhen("2026-10-22T05:50:00Z", now)).toBe("Today, 11:20");
    expect(formatWhen("2026-10-21T19:00:00Z", now)).toBe("Today, 00:30"); // already the 22nd in Kolkata
    expect(formatWhen("2026-10-21T04:10:00Z", now)).toBe("Yesterday, 09:40");
    expect(formatWhen("2026-10-10T04:10:00Z", now)).toBe("10 Oct");
    expect(formatWhen("2025-03-03T04:10:00Z", now)).toBe("3 Mar 2025");
  });

  it("names a person's role in the tenant's words when they have no job title", () => {
    expect(roleTitle(ME.user as never, ME.tenant.labels as never)).toBe("Teacher, Class 6");
    expect(roleTitle({ ...ME.user, title: null } as never, ME.tenant.labels as never)).toBe("Teacher");
    expect(roleTitle({ ...ME.user, title: null, role: "manager" } as never, ME.tenant.labels as never)).toBe(
      "Coordinator",
    );
  });

  it("labels roles in the tenant's words and builds the report header", () => {
    expect(roleLabels({ S0: "teacher", S1: "students" }, "Faculty")).toEqual({
      teacher: { label: "Faculty", analysed: true },
      students: { label: "Students" },
    });
    const header = reportRecording({ ...PAGE.items[0], title: "Fractions.mp3", type_label: "Teaching",
      unit_name: "Class 6", recorded_at: "2026-10-22T04:30:00Z", speech_ms: 2_400_000, languages: ["Hindi"],
      removed_silence: [] } as never); // prettier-ignore
    expect(header.person).toEqual({ id: "p-asha", name: "Asha", unit: "Class 6" });
  });
});

describe("sign-in button", () => {
  it("calls signInAs with the person's subject", async () => {
    const signInAs = vi.fn(async () => undefined);
    stubApi({ "/dev-idp/users": [{ subject: "dev-ravi", name: "Ravi", title: null, email: "r@x", role: "staff",
                                   tenant_id: "demo-school", tenant_name: "Demo School" }] }); // prettier-ignore
    renderAt("/login", { ...signedOut, signInAs });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in as Ravi" }));
    expect(signInAs).toHaveBeenCalledWith("dev-ravi");
  });
});
