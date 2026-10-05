import { defineConfig, devices } from "@playwright/test";

/**
 * Temporary rollback/parity suite for the retained project/scenario workflow.
 * The released suite in playwright.config.ts always exercises the constrained
 * route graph instead.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: ["**/projects.spec.ts", "**/redesign-baseline.spec.ts"],
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5174",
    env: {
      ...process.env,
      VITE_DH_COMPASS_FRONTEND_REDESIGN: "false",
    },
    url: "http://127.0.0.1:5174",
    reuseExistingServer: false,
  },
});
