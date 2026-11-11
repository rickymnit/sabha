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
const DISPUTE = {
  kind: "dispute", id: "d1", recording_id: "r8", recording_title: "Light", person_name: "Asha Rao", unit: "Class 6",
  dimension_key: "concept_clarity", dimension_name: "Concept clarity", ai_score: 4, current_score: 4,
  proposed_score: 5, comment: "Both terms were defined and checked.", status: "open", raised_by_me: false,
  raised_by_name: "Asha Rao", recorded_at: "2026-10-22T05:00:00Z",
  evidence: [{ quote: "Chlorophyll leaf ka green pigment hai", start_ms: 34_000 }], created_at: "2026-10-24T05:00:00Z",
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
        : path.startsWith("/v1/disputes?")
          ? { items: [DISPUTE], next_cursor: null }
          : path.endsWith("/resolve") && init?.method === "POST"
            ? { ...DISPUTE, status: "accepted" }
            : path.endsWith("/r8/analysis")
              ? {
                  dimensions: [
                    {
                      key: "concept_clarity",
                      name: "Concept clarity",
                      weight: 1,
                      verified: true,
                      score: 4,
                      rationale: "Defined chlorophyll but never checked it.",
                      evidence: [],
                    },
                  ],
                }
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
  it("lists disputes and paused recordings together, with a count in the menu", async () => {
    stubApi("manager");
    renderAt("/reviews");
    const queue = await screen.findByRole("list", { name: "Waiting" });
    const rows = within(queue).getAllByRole("button");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("Score dispute"), // newest first
      expect.stringContaining("Who is the teacher?"),
    ]);
    expect(screen.getByText("0 of 2 decided")).toBeInTheDocument();
    const menu = screen.getByRole("navigation", { name: "Main" });
    expect(await within(menu).findByText("2 waiting", { exact: false })).toBeInTheDocument();
    const detail = await screen.findByRole("region", { name: "Concept clarity: Light" });
    expect(within(detail).getByText("Chlorophyll leaf ka green pigment hai")).toBeInTheDocument();
    expect(await within(detail).findByText("Defined chlorophyll but never checked it.")).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByRole("group", { name: "Show" })).getByRole("button", { name: /Speakers/ }),
    );
    expect(within(screen.getByRole("list", { name: "Waiting" })).getAllByRole("button")).toHaveLength(1);
    expect(await screen.findByRole("heading", { name: "Who is the teacher?", level: 2 })).toBeInTheDocument();
  });

  it("accepts the proposed score without a note and counts the decision", async () => {
    const fetchMock = stubApi("manager");
    renderAt("/reviews?item=d:d1");
    const detail = await screen.findByRole("region", { name: "Concept clarity: Light" });
    await userEvent.click(within(detail).getByRole("button", { name: "Accept 5" }));
    const resolved = () =>
      fetchMock.mock.calls.filter(([path, init]) => path.endsWith("/resolve") && init?.method === "POST");
    await waitFor(() => expect(resolved()).toHaveLength(1));
    expect(resolved()[0]?.[0]).toBe("/v1/disputes/d1/resolve");
    expect(JSON.parse(String(resolved()[0]?.[1]?.body))).toEqual({ decision: "accepted", final_score: 5 });
    expect(await screen.findByText(/1 of \d decided/)).toBeInTheDocument();
  });

  it("asks who the teacher is and sends the chosen voice", async () => {
    const fetchMock = stubApi("manager");
    renderAt("/reviews/r9");
    expect(await screen.findByRole("heading", { name: "Who is the teacher?", level: 2 })).toBeInTheDocument();
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
    await userEvent.click(await screen.findByText("Not usable? Close it instead"));
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
