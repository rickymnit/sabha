import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/queries";
import { routes } from "../app/routes";
import { ToastProvider } from "../design";
import { StaticSessionProvider } from "../session/providers";
import type { Session } from "../session/session";
import { uploadRecording } from "./upload/upload";

vi.mock("./upload/upload", async (original) => ({
  ...(await original<typeof import("./upload/upload")>()),
  uploadRecording: vi.fn(),
}));

const labels = { person: "Teacher", person_plural: "Teachers", recording: "Lesson", recording_plural: "Lessons",
                 unit: "Class", manager: "Coordinator" }; // prettier-ignore
const me = (role: string) => ({
  user: { id: "u1", email: "m@x", name: "Meena Iyer", role, title: null, unit_ids: ["unit-6"] },
  tenant: { id: "t", name: "Demo School", profile: "school", labels, enabled_types: ["teaching", "reception"],
            units: [{ id: "unit-6", name: "Class 6" }] }, // prettier-ignore
});
const people = [
  { id: "p-asha", name: "Asha Rao", unit_id: "unit-6" },
  { id: "p-ravi", name: "Ravi Kumar", unit_id: "unit-6" },
];

function stubApi(role: string, visible = people) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const body = path.startsWith("/v1/me") ? me(role) : path.startsWith("/v1/people") ? visible : { items: [] };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
}

function renderUpload() {
  const session: Session = { mode: "dev", token: "t", ready: true, signOut: vi.fn() };
  const router = createMemoryRouter(routes, { initialEntries: ["/upload"] });
  render(
    <StaticSessionProvider session={session}>
      <ToastProvider>
        <QueryClientProvider client={createQueryClient()}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ToastProvider>
    </StaticSessionProvider>,
  );
}

const lesson = (name: string) => new File(["abc"], name, { type: "audio/mpeg" });

beforeEach(() => {
  localStorage.clear();
  vi.mocked(uploadRecording).mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("the upload page", () => {
  it("uploads each file with the chosen type, person and consent, then says what happens next", async () => {
    stubApi("manager");
    vi.mocked(uploadRecording)
      .mockResolvedValueOnce({ kind: "done", result: { recording_id: "r1", status: "UPLOADED", awaiting_consent: false, duplicate_of: null } }) // prettier-ignore
      .mockResolvedValueOnce({ kind: "done", result: { recording_id: "r2", status: "UPLOADED", awaiting_consent: false, duplicate_of: null } }); // prettier-ignore
    const user = userEvent.setup();
    renderUpload();
    await user.upload(await screen.findByLabelText("Choose files"), [lesson("Fractions.mp3"), lesson("Decimals.mp3")]);
    expect(screen.getByText("2 ready")).toBeInTheDocument();

    const start = screen.getByRole("button", { name: "Upload 2 lessons" });
    expect(start).toBeDisabled(); // no teacher chosen yet
    await user.click(screen.getByRole("radio", { name: "Reception" }));
    await user.selectOptions(await screen.findByRole("combobox", { name: "Teacher" }), "p-ravi");
    await user.click(screen.getByRole("checkbox", { name: /Consent is on file/ }));
    expect(start).toBeDisabled(); // consent ticked but not named
    await user.type(screen.getByRole("textbox", { name: "Consent form or notice" }), "Front desk notice 2026");
    await user.click(start);

    expect(await screen.findByText(/All uploaded/)).toBeInTheDocument();
    expect(uploadRecording).toHaveBeenCalledTimes(2);
    expect(vi.mocked(uploadRecording).mock.calls[0]?.[0]).toMatchObject({
      type: "reception", personId: "p-ravi", consentRef: "Front desk notice 2026",
    }); // prettier-ignore
    expect(screen.getAllByText(/Sabha is processing it now/)).toHaveLength(2);
    expect(localStorage.getItem("sabha.upload.consent_ref")).toBe("Front desk notice 2026"); // remembered
  });

  it("says a file without consent will wait, and keeps a failed file to try again", async () => {
    stubApi("staff", people.slice(0, 1));
    vi.mocked(uploadRecording).mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup();
    renderUpload();
    expect(await screen.findByText("Asha Rao (you)")).toBeInTheDocument(); // staff upload only for themselves
    await user.upload(screen.getByLabelText("Choose files"), [lesson("Fractions.mp3")]);
    expect(screen.getByText("These will wait for consent before processing.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Upload 1 lesson" }));
    const files = await screen.findByRole("list", { name: "Files" });
    expect(await within(files).findByText(/upload was interrupted/)).toBeInTheDocument();
    expect(vi.mocked(uploadRecording).mock.calls[0]?.[0]).toMatchObject({ personId: "p-asha", consentRef: null });
    await user.click(within(files).getByRole("button", { name: "Try again" }));
    expect(within(files).getByText("Ready to upload")).toBeInTheDocument();
  });
});
