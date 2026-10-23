import { defineConfig, devices } from "@playwright/test";

// Browser smoke tests against the running dev stack (`make e2e`; the stack and its start-up are in README.md).
// One worker: the tests share the dev database. Desktop and phone widths, as the designs are checked.
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts", // not *.test.ts, so Vitest never picks these up
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5180",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: { command: "pnpm dev", url: "http://localhost:5180", reuseExistingServer: true, timeout: 60_000 },
});
