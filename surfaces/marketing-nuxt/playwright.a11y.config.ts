import { defineConfig } from "@playwright/test";

const appPort = 3011;
const backendPort = 9012;
const managed = process.env.MARKETING_E2E_MANAGED === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/a11y.spec.ts",
  outputDir: "./test-results/a11y",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  expect: { timeout: 10_000 },
  webServer: managed
    ? [
        {
          command: `python3 tests/visual/mock_backend.py ${backendPort}`,
          name: "backend hermético",
          wait: { stdout: new RegExp(`marketing visual mock listening on ${backendPort}`) },
          reuseExistingServer: false,
          timeout: 30_000,
        },
        {
          command:
            `NUXT_IGNORE_LOCK=1 NUXT_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
            `NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
            `npx nuxt dev --host 127.0.0.1 --port ${appPort}`,
          url: `http://127.0.0.1:${appPort}/`,
          reuseExistingServer: false,
          timeout: 120_000,
        },
      ]
    : undefined,
  use: {
    baseURL:
      process.env.MARKETING_E2E_BASE_URL ??
      `http://127.0.0.1:${managed ? appPort : 3007}`,
    browserName: "chromium",
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
