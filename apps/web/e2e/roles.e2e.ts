// What each role can open, in a real browser against the running stack (P6.8). Done when: a staff account cannot
// open a colleague's report. The API refuses it (tests/security/permissions.yaml); this checks the whole path a
// person takes, link included. Reading tests use the demo school; the colleague test uses the hidden E2E School
// (scripts/admin/dev_seed.py), so nothing it creates appears in the demo.

import { expect, test, type Page } from "@playwright/test";

const DEV_TOKEN_KEY = "sabha.dev_token"; // src/session/session.ts
const API_READY = "http://localhost:8000/ready";

test.beforeAll(async ({ request }) => {
  const ready = await request.get(API_READY).catch(() => null);
  expect(
    ready?.ok(),
    "The stack is not running: make dev, make api, then `uv run python scripts/admin/dev_seed.py` (README.md)",
  ).toBe(true);
});

async function openMenu(page: Page) {
  const button = page.getByRole("button", { name: "Open menu" });
  if (await button.isVisible()) await button.click();
}

async function signInAs(page: Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: `Sign in as ${name}` }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

async function tokenFor(page: Page, subject: string): Promise<string> {
  const response = await page.request.post("/dev-idp/token", { data: { subject } });
  expect(response.ok(), "Run scripts/admin/dev_seed.py to create E2E School").toBe(true);
  return ((await response.json()) as { access_token: string }).access_token;
}

async function menuPages(page: Page): Promise<string[]> {
  await openMenu(page);
  const menu = page.getByRole("navigation", { name: "Main" });
  await expect(menu.getByRole("link").first()).toBeVisible();
  const types = ["Teaching", "Reception", "Counselling", "Meeting", "Sales"];
  return (await menu.getByRole("link").allTextContents())
    .map((text) => text.replace(/\d+(, \d+)?$/, "").trim()) // drop the counts and badges
    .filter((text) => !types.includes(text));
}

test("the principal has every page, settings included", async ({ page }) => {
  await signInAs(page, "Priya Sharma");
  expect(await menuPages(page)).toEqual([
    "Overview",
    "Lessons",
    "Reviews",
    "Teachers",
    "Rubrics",
    "Upload",
    "Activity",
    "Settings",
  ]);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
  await expect(page.getByLabel("Organisation name")).toBeVisible();
});

test("a coordinator has their units' pages but not settings", async ({ page }) => {
  await signInAs(page, "Meena Iyer");
  expect(await menuPages(page)).toEqual(["Overview", "Lessons", "Reviews", "Teachers", "Rubrics", "Upload"]);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Only owners and administrators can change settings" })).toBeVisible();
});

test("a teacher has their lessons, the rubrics and upload, and can read how they are scored", async ({ page }) => {
  await signInAs(page, "Asha Rao");
  expect(await menuPages(page)).toEqual(["Lessons", "Rubrics", "Upload"]);
  await openMenu(page);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Rubrics" }).click();
  await expect(page.getByRole("heading", { name: "Teaching rubric", level: 1 })).toBeVisible();
  await expect(page.getByRole("table", { name: "Dimensions" })).toBeVisible();
  await page.goto("/overview");
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("Overview");
});

test("a teacher cannot open a colleague's report", async ({ page }) => {
  // The colleague creates a recording (an upload that has only started is enough: it exists and is theirs).
  const colleague = await tokenFor(page, "e2e-colleague");
  const created = await page.request.post("/v1/recordings", {
    headers: { Authorization: `Bearer ${colleague}`, "Idempotency-Key": crypto.randomUUID() },
    data: { type: "teaching", file_name: "Colleague lesson.mp3", size_bytes: 1024, content_type: "audio/mpeg",
            consent_ref: "E2E test notice" }, // prettier-ignore
  });
  expect(created.status(), await created.text()).toBe(201);
  const { recording_id } = (await created.json()) as { recording_id: string };

  // The colleague can open it; the other teacher, with the same link, cannot.
  const own = await page.request.get(`/v1/recordings/${recording_id}`, {
    headers: { Authorization: `Bearer ${colleague}` },
  });
  expect(own.status()).toBe(200);
  const teacher = await tokenFor(page, "e2e-teacher");
  const theirs = await page.request.get(`/v1/recordings/${recording_id}`, {
    headers: { Authorization: `Bearer ${teacher}` },
  });
  expect(theirs.status()).toBe(404);

  await page.addInitScript(([key, token]) => sessionStorage.setItem(key, token), [DEV_TOKEN_KEY, teacher]);
  await page.goto(`/recordings/${recording_id}`);
  await expect(page.getByRole("heading", { name: "We couldn't find this lesson", level: 1 })).toBeVisible();
  await expect(page.getByText("Colleague lesson")).toHaveCount(0);
  await expect(page.getByText("Test Colleague")).toHaveCount(0);
  await page.getByRole("button", { name: "Go to lessons" }).click();
  await expect(page.getByRole("heading", { name: "Lessons", level: 1 })).toBeVisible();
});

test("playing a lesson's audio shows in the owner's activity log", async ({ page }) => {
  await signInAs(page, "Priya Sharma");
  await page.goto("/recordings");
  const analysed = page.getByRole("row").filter({ hasText: "Analysed" });
  await expect(page.getByRole("row").nth(1)).toBeVisible();
  test.skip((await analysed.count()) === 0, "The demo school has no analysed lesson yet");
  const title = (await analysed.first().getByRole("link").first().textContent())?.trim() ?? "";
  await analysed.first().getByRole("link").first().click();
  await page.getByRole("button", { name: "Play", exact: true }).click(); // issuing the playback link is audited

  await openMenu(page);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Activity" }).click();
  await page.getByLabel("What").selectOption({ label: "Played audio" });
  const newest = page.getByRole("table", { name: "Activity" }).getByRole("row").nth(1);
  await expect(newest).toContainText("Priya Sharma");
  await expect(newest).toContainText(`Played the audio of ${title}`);
  await expect(newest).toContainText(/Today/);
});
