// Accessibility check (P6.8): every main page, as the role that uses it, goes through axe-core with the WCAG 2.1 A
// and AA rules plus axe's best practices. Colour contrast needs real layout and colours, which jsdom does not
// compute, so test/contrast.test.ts checks the token pairs instead; every other rule runs here.

import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/queries";
import { routes } from "../app/routes";
import { ToastProvider } from "../design";
import { RecordingReport } from "../features/report";
import { mockLesson, mockReport } from "../features/report/mock";
import { StaticSessionProvider } from "../session/providers";
import type { Session } from "../session/session";
import { installMediaMock } from "./media";

const LABELS = { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                 unit: "Class", manager: "Coordinator" }; // prettier-ignore

function me(role: string) {
  return {
    user: { id: "u-1", email: "p@demo.example", name: "Priya Kapoor", role, title: null, unit_ids: ["unit-6"] },
    tenant: { id: "t", name: "Demo School", profile: "school", labels: LABELS, enabled_types: ["teaching", "reception"],
              units: [{ id: "unit-6", name: "Class 6" }] }, // prettier-ignore
  };
}

const ITEM = { id: "r1", title: "Fractions", type: "teaching", status: "COMPLETED", status_reason: null,
               status_note: null, person: { id: "p-asha", name: "Asha" }, unit_id: "unit-6", file_name: "Fractions.mp3",
               duration_ms: 2_700_000, created_at: "2026-10-22T04:30:00Z", status_changed_at: null,
               completed_at: null, overall_score: 3.6 }; // prettier-ignore
const PAGE = { items: [ITEM], next_cursor: null };
const API: Record<string, unknown> = {
  "/v1/recordings/counts": { by_type: { teaching: 1 } },
  "/v1/recordings": PAGE,
  "/v1/usage": { plan: "starter", used_hours: 38.4, allowance_hours: 100, state: "ok", message: null,
                 resets_at: "2026-10-31T18:30:00Z" }, // prettier-ignore
  "/v1/overview": { from: "2026-09-23T18:30:00Z", to: "2026-10-23T18:30:00Z", recordings_analysed: 1, audio_hours: 0.75,
                    median_overall_by_type: [{ type: "teaching", median: 3.6, n: 1 }], coaching: [],
                    in_progress: [] }, // prettier-ignore
  "/v1/people/summary": [{ id: "p-asha", name: "Asha", unit_id: "unit-6", user_id: null, recordings_analysed: 1,
                           latest_score: 3.6, latest_at: "2026-10-22T04:30:00Z", recent_scores: [3.2, 3.6] }], // prettier-ignore
  "/v1/people": [{ id: "p-asha", name: "Asha", unit_id: "unit-6", user_id: null }],
  "/v1/reviews": { items: [], next_cursor: null },
  "/v1/audit": { items: [{ id: "a1", at: "2026-10-27T05:00:00Z", action: "recording.play",
                           actor: { id: "u-1", name: "Priya Kapoor", role: "owner" },
                           target: { type: "recording", id: "r1", label: "Fractions" }, meta: {} }],
                 next_cursor: null }, // prettier-ignore
  "/v1/disputes": { items: [], next_cursor: null },
  "/v1/rubrics/teaching.school.v0.1": {
    id: "teaching.school.v0.1", type: "teaching", version: "0.1", in_use: true, previous_id: null, changes: [],
    versions: [{ id: "teaching.school.v0.1", version: "0.1", in_use: true }],
    dimensions: [{ key: "clarity", name: "Concept clarity", weight: 1, definition: "States the main idea.", min_quotes: 1,
                   not_applicable_when: null,
                   scale: [1, 2, 3, 4, 5].map((level) => ({ level, description: `Level ${level}`, example: null })) }],
  }, // prettier-ignore
  "/v1/rubrics": { items: [{ type: "teaching", current_id: "teaching.school.v0.1", dimension_count: 1,
                             versions: [{ id: "teaching.school.v0.1", version: "0.1", in_use: true }] }] }, // prettier-ignore
  "/v1/settings": { name: "Demo School", profile: "school", plan: "starter", labels: LABELS,
                    enabled_types: ["teaching", "reception"], max_types: 2, retention_days: 90,
                    types: ["teaching", "counselling", "reception", "meeting", "sales"].map((type) => ({
                      type, enabled: type === "teaching" || type === "reception",
                      available: type === "teaching" || type === "reception" })) }, // prettier-ignore
  "/dev-idp/users": [{ subject: "dev-asha", name: "Asha Rao", title: "Teacher, Class 6", email: "a@x", role: "staff",
                       tenant_id: "t", tenant_name: "Demo School" }], // prettier-ignore
};

function stubApi(role: string) {
  const answers: Record<string, unknown> = { ...API, "/v1/me": me(role) };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const key = Object.keys(answers)
        .filter((prefix) => path.startsWith(prefix))
        .sort((a, b) => b.length - a.length)[0];
      if (!key) return new Response(JSON.stringify({ code: "not_found", title: "Not found" }), { status: 404 });
      return new Response(JSON.stringify(answers[key]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

async function violations(container: Element): Promise<string[]> {
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.map((n) => `${n.html.slice(0, 100)} -- ${n.failureSummary ?? ""}`).join("\n  ")}`,
  );
}

afterEach(() => vi.unstubAllGlobals());

const PAGES: [string, string, string | RegExp][] = [
  // [address, role, the heading that says the page is ready]
  ["/login", "staff", "Welcome"],
  ["/recordings", "staff", "Lessons"],
  ["/overview", "owner", /^Good (morning|afternoon|evening), /],
  ["/people", "manager", "Teachers"],
  ["/reviews", "reviewer", "Reviews"],
  ["/rubrics/teaching.school.v0.1", "staff", "Teaching rubric"],
  ["/settings", "owner", "Settings"],
  ["/activity", "admin", "Activity"],
  ["/upload", "staff", "Upload recordings"],
  ["/no-such-page", "staff", "We couldn't find that page"],
];

describe("accessibility", () => {
  it.each(PAGES)("%s (as %s) passes the automatic checks", async (path, role, heading) => {
    stubApi(role);
    const session: Session = {
      mode: "dev",
      token: path === "/login" ? undefined : "token",
      ready: true,
      signInAs: vi.fn(),
      signOut: vi.fn(),
    };
    const router = createMemoryRouter(routes, { initialEntries: [path] });
    const { container } = render(
      <StaticSessionProvider session={session}>
        <ToastProvider>
          <QueryClientProvider client={createQueryClient()}>
            <RouterProvider router={router} />
          </QueryClientProvider>
        </ToastProvider>
      </StaticSessionProvider>,
    );
    await screen.findByRole("heading", { level: 1, name: heading }, { timeout: 4000 });
    await act(async () => {}); // let the menu's numbers arrive too
    expect(await violations(container)).toEqual([]);
  });

  it("the report page passes the automatic checks", async () => {
    const media = installMediaMock();
    try {
      const lesson = mockLesson();
      const { container } = render(
        <RecordingReport
          recording={lesson.recording}
          analysis={mockReport(lesson)}
          transcript={lesson.transcript}
          labels={lesson.labels}
          roles={lesson.roles}
          viewerRole="manager"
          getPlaybackUrl={async () => ({ url: "https://audio.example/a.opus", expires_at: "2099-01-01T00:00:00Z" })}
        />,
      );
      await act(async () => {});
      expect(await violations(container)).toEqual([]);
    } finally {
      media.restore();
    }
  });
});
