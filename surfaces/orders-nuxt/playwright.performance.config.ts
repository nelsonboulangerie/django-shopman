import { defineConfig, devices } from "@playwright/test";
if (process.env.ORDERS_PERF_LAB !== "1") throw new Error("Use only the separate synthetic HTTP performance lab");
export default defineConfig({
  testDir: "./tests/performance", timeout: 120000, expect: { timeout: 10000 },
  fullyParallel: false, workers: 1, retries: 0, reporter: [["list"]],
  outputDir: "../../.orders-lab/performance-browser-results",
  use: { actionTimeout: 10000, navigationTimeout: 15000, baseURL: "http://127.0.0.1:3005", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
