import { defineConfig } from "@playwright/test";

// Trava de sobreposição do Compras (`tests/overlap`): o mesmo backend hermético e o mesmo
// build de produção da matriz visual (`playwright.visual.config.ts`), mas sem o reporter
// de evidência nem o globalSetup do kit. O globalSetup só confere o Chromium pinado para
// baseline de retrato, e aqui não há baseline: é geometria. Portas próprias, para rodar
// ao lado da fase visual sem colidir.

const appPort = Number(process.env.PURCHASE_OVERLAP_APP_PORT || 41008);
const backendPort = Number(process.env.PURCHASE_OVERLAP_BACKEND_PORT || 41808);

export default defineConfig({
  testDir: "./tests/overlap",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results/overlap",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  webServer: [
    {
      command: "node tests/visual/mockBackend.mjs",
      port: backendPort,
      reuseExistingServer: false,
      timeout: 30_000,
      env: { MOCK_PORT: String(backendPort) },
    },
    {
      command:
        "npx nuxt build && " +
        "HOST=127.0.0.1 PORT=" + appPort + " " +
        "NUXT_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
        "NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
        "node .output/server/index.mjs",
      url: "http://127.0.0.1:" + appPort + "/",
      reuseExistingServer: false,
      timeout: 420_000,
    },
  ],
  use: {
    browserName: "chromium",
    headless: true,
    baseURL: "http://127.0.0.1:" + appPort,
    bypassCSP: true,
    colorScheme: "light",
    locale: "pt-BR",
    reducedMotion: "reduce",
    serviceWorkers: "block",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
  },
});
