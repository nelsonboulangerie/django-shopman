import { defineConfig } from "@playwright/test";

const appPort = 3010;
const backendPort = 9011;

export default defineConfig({
  testDir: "./tests/visual",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results/visual",
  snapshotPathTemplate: "{testDir}/baselines/{arg}{ext}",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.001,
      threshold: 0.2,
    },
  },
  webServer: [
    {
      command: `python3 tests/visual/mock_backend.py ${backendPort}`,
      url: `http://127.0.0.1:${backendPort}/admin/login/`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command:
        `NUXT_IGNORE_LOCK=1 MARKETING_VISUAL_CLIENT_ONLY=1 ` +
        `MARKETING_VISUAL_MATRIX=1 ` +
        `NUXT_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
        `NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
        `npx nuxt dev --host 127.0.0.1 --port ${appPort}`,
      url: `http://127.0.0.1:${appPort}/`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  use: {
    baseURL: `http://127.0.0.1:${appPort}`,
    browserName: "chromium",
    headless: true,
    bypassCSP: true,
    colorScheme: "light",
    locale: "pt-BR",
    reducedMotion: "reduce",
    serviceWorkers: "block",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
    viewport: { width: 390, height: 844 },
  },
});
