import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./test-results/a11y",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.MARKETING_E2E_BASE_URL ?? "http://127.0.0.1:3007",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    bypassCSP: true,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
    viewport: { width: 320, height: 568 },
    reducedMotion: "reduce",
    colorScheme: "light",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
