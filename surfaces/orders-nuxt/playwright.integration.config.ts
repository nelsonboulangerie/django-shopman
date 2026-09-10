import { defineConfig, devices } from "@playwright/test";
if (process.env.ORDERS_LAB_INTEGRATION !== "1") throw new Error("Start the isolated synthetic Orders lab before this integration suite.");
export default defineConfig({
  testDir: "./tests/integration", testMatch: "**/*.spec.ts", timeout: 45000,
  expect: { timeout: 10000 }, fullyParallel: false, retries: 0,
  reporter: [["list"]], outputDir: "../../.orders-lab/playwright-results",
  use: { baseURL: "http://127.0.0.1:3004", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: { command: "node .output/server/index.mjs", port: 3004, reuseExistingServer: false,
    env: { NUXT_APP_BASE_URL: "/", NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8014", NUXT_PUBLIC_DJANGO_BASE_URL: "http://127.0.0.1:8014", HOST: "127.0.0.1", PORT: "3004" } },
});
