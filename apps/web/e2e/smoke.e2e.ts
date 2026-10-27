// Browser smoke tests: the paths someone showing Sabha takes, in a real browser against the running stack. Reading
// tests use the demo school's accounts and change nothing; the upload test signs in to the hidden E2E School
// (scripts/admin/dev_seed.py), so test files never appear in the demo.

import { expect, test, type Page } from "@playwright/test";

const DEV_TOKEN_KEY = "sabha.dev_token"; // src/session/session.ts
const API_READY = "http://localhost:8000/ready"; // `make api`; the web dev server does not forward /ready

test.beforeAll(async ({ request }) => {
  const ready = await request.get(API_READY).catch(() => null);
  expect(
    ready?.ok(),
    "The stack is not running: make dev, make api, then `uv run python scripts/admin/dev_seed.py` (README.md)",
  ).toBe(true);
});

/** Opens the phone menu when there is one, so menu links are visible at every width. */
async function openMenu(page: Page) {
  const button = page.getByRole("button", { name: "Open menu" });
  if (await button.isVisible()) await button.click();
}

async function signInAs(page: Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: `Sign in as ${name}` }).click();
  // On phones the menu stays closed until asked for, so wait for the first page instead.
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

/** Signs in without the sign-in page: for E2E School, whose people the page does not list. */
async function signInWithToken(page: Page, subject: string) {
  const response = await page.request.post("/dev-idp/token", { data: { subject } });
  expect(response.ok(), "Run scripts/admin/dev_seed.py to create E2E School").toBe(true);
  const { access_token } = (await response.json()) as { access_token: string };
  await page.addInitScript(([key, token]) => sessionStorage.setItem(key, token), [DEV_TOKEN_KEY, access_token]);
}

test("the sign-in page lists the demo school's accounts and no test accounts", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Welcome" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sign in as / }).first()).toBeVisible();
  await expect(page.getByText("Test Teacher")).toHaveCount(0);
  await expect(page.getByText(/local development|APP_ENV/)).toHaveCount(0);
});

test("the principal lands on the Overview and every menu page opens", async ({ page }) => {
  await signInAs(page, "Priya Sharma");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Processing now" })).toBeVisible();

  for (const [link, heading] of [
    ["Lessons", "Lessons"],
    ["Teachers", "Teachers"],
    ["Upload", "Upload recordings"],
    ["Overview", "Overview"],
  ]) {
    await openMenu(page);
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: link, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expect(page.getByText(/later step of the build/)).toHaveCount(0);
  }
});

test("a teacher lands on their lessons and a report opens with scores and transcript", async ({ page }) => {
  await signInAs(page, "Asha Rao");
  await expect(page).toHaveURL(/\/recordings$/);
  await expect(page.getByRole("heading", { name: "Lessons", level: 1 })).toBeVisible();
  await openMenu(page);
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Teachers" })).toHaveCount(0);

  const analysed = page.getByRole("row").filter({ hasText: "Analysed" });
  await expect(page.getByRole("row").nth(1)).toBeVisible(); // the list has loaded
  test.skip((await analysed.count()) === 0, "The demo school has no analysed lesson yet");
  await analysed.first().getByRole("link").first().click();
  await expect(page.getByText("Overall score")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Rubric scores" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Transcript", exact: true })).toBeVisible();
  await expect(page.getByText(/At utterance u\d{4}/)).toHaveCount(0);
});

test("an unknown address shows a way back, not a dead end", async ({ page }) => {
  await signInAs(page, "Meena Iyer");
  await page.goto("/plans");
  await expect(page.getByRole("heading", { name: "We couldn't find that page" })).toBeVisible();
  await page.getByRole("button", { name: "Go to lessons" }).click();
  await expect(page.getByRole("heading", { name: "Lessons", level: 1 })).toBeVisible();
});

test("a teacher uploads a recording straight to storage and it appears in their lessons", async ({ page }) => {
  await signInWithToken(page, "e2e-teacher");
  await page.goto("/upload");
  await expect(page.getByText("Test Teacher (you)")).toBeVisible();

  await page.getByLabel("Choose files").setInputFiles("e2e/fixtures/E2E silence.wav");
  await expect(page.getByText("Ready to upload")).toBeVisible();
  await page.getByRole("checkbox", { name: /Consent is on file/ }).check();
  await page.getByRole("textbox", { name: "Consent form or notice" }).fill("E2E test notice");
  await page.getByRole("button", { name: "Upload 1 lesson" }).click();
  // The fixture is the same file every run, so an earlier run's copy may still be in E2E School: then the page
  // asks before uploading a duplicate, which is the behaviour to check too.
  const uploaded = page.getByText("Uploaded. Sabha is processing it now.");
  const duplicate = page.getByText("This file has been uploaded before.");
  await expect(uploaded.or(duplicate)).toBeVisible({ timeout: 30_000 });
  if (await duplicate.isVisible()) await page.getByRole("button", { name: "Upload it again" }).click();
  await expect(uploaded).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: "Go to lessons" }).click();
  await expect(page.getByRole("link", { name: "E2E silence" }).first()).toBeVisible();
});
