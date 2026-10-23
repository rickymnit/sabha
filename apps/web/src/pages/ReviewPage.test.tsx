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
const me = (role: string) => ({
  user: { id: "u1", email: "m@x", name: "Meena Iyer", role, title: null, unit_ids: ["unit-6"] },
  tenant: { id: "t", name: "Demo School", profile: "school", labels, enabled_types: ["teaching"],
            units: [{ id: "unit-6", name: "Class 6" }] }, // prettier-ignore
});
const ITEM = {
  id: "r9", title: "Waves", type: "teaching", status: "NEEDS_REVIEW", status_reason: "unclear_roles",
  status_note: "We could not tell the speakers apart reliably.", person: { id: "p-asha", name: "Asha Rao" },
  unit_id: "unit-6", file_name: "Waves.mp3", duration_ms: 180_000, created_at: "2026-10-23T05:00:00Z",
  status_changed_at: "2026-10-23T05:10:00Z", completed_at: null, overall_score: null,
}; // prettier-ignore
const DETAIL = { ...ITEM, type_label: "Teaching", unit_name: "Class 6", recorded_at: ITEM.created_at, speech_ms: 1,
                 languages: [], removed_silence: [] }; // prettier-ignore
const SPEAKERS = {
  recording_id: "r9", reason: "unclear_roles", choices: ["teacher", "students"],
  speakers: [
    { label: "S0", guess: "teacher", talk_ms: 60_000, share: 0.5, samples: [{ start_ms: 0, end_ms: 9_000, text: "Sab samajh aaya?" }] },
    { label: "S1", guess: "students", talk_ms: 60_000, share: 0.5, samples: [{ start_ms: 39_000, end_ms: 45_000, text: "Aaj hum waves padhenge." }] },
  ],
}; // prettier-ignore

function stubApi(role: string, status = "NEEDS_REVIEW") {
  const fetchMock = vi.fn<(path: string, init?: RequestInit) => Promise<Response>>(async (path, init) => {
    const body = path.startsWith("/v1/me")
      ? me(role)
      : path.startsWith("/v1/reviews")
        ? { items: status === "NEEDS_REVIEW" ? [ITEM] : [], next_cursor: null }
        : path.endsWith("/speakers")
          ? SPEAKERS
          : path.endsWith("/transcript")
            ? { playback_url: "https://storage.example/p.opus", playback_expires_in_s: 900 }
            : path.endsWith("/review") && init?.method === "POST"
              ? { recording_id: "r9", status: "TRANSCRIBING" }
              : path.startsWith("/v1/recordings/r9")
                ? { ...DETAIL, status }
                : { items: [], next_cursor: null };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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

const posted = (fetchMock: ReturnType<typeof stubApi>) =>
  fetchMock.mock.calls.filter(([path, init]) => path.endsWith("/review") && init?.method === "POST");

afterEach(() => vi.unstubAllGlobals());

describe("reviews", () => {
  it("lists what waits for review, with a count in the menu, and opens a review", async () => {
    stubApi("manager");
    const router = renderAt("/reviews");
    expect(await screen.findByText("We could not tell the speakers apart reliably.")).toBeInTheDocument();
    const menu = screen.getByRole("navigation", { name: "Main" });
    expect(await within(menu).findByText("1 waiting", { exact: false })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Waves" }));
    expect(router.state.location.pathname).toBe("/reviews/r9");
  });

  it("asks who the teacher is and sends the chosen voice", async () => {
    const fetchMock = stubApi("manager");
    renderAt("/reviews/r9");
    expect(await screen.findByRole("heading", { name: "Who is the teacher?" })).toBeInTheDocument();
    const confirm = await screen.findByRole("button", { name: "Confirm and score" });
    expect(confirm).toBeDisabled();
    const voices = await screen.findAllByRole("radio");
    expect(screen.getByText(/Sabha guessed: Teacher/)).toBeInTheDocument(); // the guess, in the tenant's word
    await userEvent.click(voices[1] as HTMLElement); // the reviewer disagrees with the guess
    await userEvent.click(confirm);
    await waitFor(() => expect(posted(fetchMock)).toHaveLength(1));
    expect(JSON.parse(String(posted(fetchMock)[0]?.[1]?.body))).toEqual({
      action: "confirm_roles",
      staff_speaker: "S1",
    });
  });

  it("closes a recording only with a note", async () => {
    const fetchMock = stubApi("admin");
    renderAt("/reviews/r9");
    const close = await screen.findByRole("button", { name: "Close as not usable" });
    expect(close).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Why is it not usable?" }), "Recorder in a bag");
    await userEvent.click(close);
    await waitFor(() => expect(posted(fetchMock)).toHaveLength(1));
    expect(JSON.parse(String(posted(fetchMock)[0]?.[1]?.body))).toEqual({ action: "close", note: "Recorder in a bag" });
  });

  it("says when a review is already done", async () => {
    stubApi("manager", "TRANSCRIBING");
    renderAt("/reviews/r9");
    expect(await screen.findByRole("heading", { name: "This review is done" })).toBeInTheDocument();
  });

  it("is not in a teacher's menu", async () => {
    stubApi("staff");
    renderAt("/recordings");
    const menu = await screen.findByRole("navigation", { name: "Main" });
    await within(menu).findByText("Meena Iyer");
    expect(within(menu).queryByRole("link", { name: /Reviews/ })).toBeNull();
  });
});
