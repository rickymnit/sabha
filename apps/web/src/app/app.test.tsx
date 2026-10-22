import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../design";
import { reportRecording, roleLabels } from "../pages/recordingView";
import { DevSessionProvider, StaticSessionProvider } from "../session/providers";
import { authMode, DEV_TOKEN_KEY, type Session } from "../session/session";
import { formatDuration, statusChip, viewerRole } from "./format";
import { createQueryClient } from "./queries";
import { routes } from "./routes";

const ME = {
  user: { id: "u-asha", email: "asha@demo.example", name: "Asha Rao", role: "staff", unit_ids: ["unit-6"] },
  tenant: {
    id: "demo-school",
    name: "Demo School",
    profile: "school",
    labels: { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
              unit: "Class", manager: "Coordinator" }, // prettier-ignore
    enabled_types: ["teaching", "reception"],
  },
};
const PAGE = {
  items: [
    { id: "r1", type: "teaching", status: "COMPLETED", status_reason: null, person: { id: "p-asha", name: "Asha" },
      unit_id: "unit-6", file_name: "Fractions.mp3", duration_ms: 2_700_000, created_at: "2026-10-22T04:30:00Z",
      status_changed_at: null, completed_at: null, overall_score: 3.6 }, // prettier-ignore
    { id: "r2", type: "teaching", status: "TRANSCRIBING", status_reason: null, person: { id: "p-asha", name: "Asha" },
      unit_id: "unit-6", file_name: "Decimals.mp3", duration_ms: null, created_at: "2026-10-22T05:00:00Z",
      status_changed_at: null, completed_at: null, overall_score: null }, // prettier-ignore
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
    stubApi({ "/dev-idp/users": [{ subject: "dev-asha", name: "Asha Rao (Teacher)", email: "a@x", role: "staff",
                                   tenant_id: "demo-school", tenant_name: "Demo School" }] }); // prettier-ignore
    renderAt("/recordings", signedOut);
    expect(await screen.findByRole("heading", { name: /sign in \(local development\)/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Sign in as Asha Rao (Teacher)" })).toBeInTheDocument();
  });

  it("shows the list in the tenant's own words, with statuses and scores", async () => {
    const fetchMock = stubApi({ "/v1/me": ME, "/v1/recordings": PAGE });
    renderAt("/recordings", signedIn);
    expect(await screen.findByRole("heading", { name: "Lessons" })).toBeInTheDocument();
    expect(await screen.findByText("Fractions.mp3")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Teacher" })).toBeInTheDocument();
    expect(screen.getByText("Analysed")).toBeInTheDocument();
    expect(screen.getByText("Transcribing")).toBeInTheDocument();
    expect(screen.queryByText(/lecture|class session/i)).not.toBeInTheDocument();
    const auth = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Record<string, string>;
    expect(auth.Authorization).toBe("Bearer token-asha");
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
    stubApi({ "/dev-idp/users": [{ subject: "dev-ravi", name: "Ravi", email: "r@x", role: "staff",
                                   tenant_id: "demo-school", tenant_name: "Demo School" }] }); // prettier-ignore
    renderAt("/login", { ...signedOut, signInAs });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in as Ravi" }));
    expect(signInAs).toHaveBeenCalledWith("dev-ravi");
  });
});
