import { defineConfig, devices } from "@playwright/test";

// E2E do Produção (backend-independente). O mock backend serve uma sessão autenticada + um
// board de produção → as telas de operador renderizam, mais os estados vazio/erro e o
// corte do menuboard paralelo. Build com baseURL '/' (produção usa '/'). Login efetivo,
// lock (Opção C) e ações reais rodam contra o Django real (reviewer local) — ver
// tests/e2e/README.
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results/browser",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    // Porta de e2e dedicada (3105), distinta do dev server (3005) — o build de produção do
    // e2e sobe aqui e aponta ao mock, sem colidir/reusar um dev server aberto em :3005.
    baseURL: "http://127.0.0.1:3105",
    bypassCSP: true,
    colorScheme: "light",
    locale: "pt-BR",
    screenshot: "only-on-failure",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-tablet-landscape",
      metadata: { touchTargets: true },
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1024, height: 768 },
      },
    },
    {
      name: "webkit-tablet-portrait",
      metadata: { touchTargets: true },
      use: {
        browserName: "webkit",
        hasTouch: true,
        viewport: { width: 768, height: 1024 },
      },
    },
    {
      name: "chromium-desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "chromium-tv-full-hd",
      metadata: { board: true },
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1920, height: 1080 },
      },
    },
    {
      name: "chromium-tv-1366",
      metadata: { board: true },
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1366, height: 768 },
      },
    },
    {
      name: "chromium-mobile-manager",
      metadata: { touchTargets: true },
      use: {
        ...devices["Desktop Chrome"],
        hasTouch: true,
        viewport: { width: 390, height: 844 },
      },
    },
  ],
  webServer: [
    {
      command: "node tests/e2e/mockBackend.mjs",
      port: 8797,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "nuxt build && node .output/server/index.mjs",
      port: 3105,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8797",
        // Exceção deliberada e testável: Nuxt build usa NODE_ENV=production, mas
        // somente o harness E2E pode falar com upstream HTTP local.
        SHOPMAN_ENVIRONMENT: "test",
        SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM: "1",
        HOST: "127.0.0.1",
        PORT: "3105",
      },
    },
  ],
});
