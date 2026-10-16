import { defineConfig, devices } from "@playwright/test";

// Carga direta com SSR no build de PRODUÇÃO (`.output`, o que vai ao ar), contra o
// backend hermético da matriz visual. A matriz visual roda em modo client-only e
// nunca viu a hidratação; foi assim que a Fila presa no esqueleto e a toolbar sumida
// no celular (09/10/2026) chegaram ao alpha. Rode `npm run build` antes.

const appPort = Number(process.env.ORDERS_SSR_PORT || 34816);
const backendPort = Number(process.env.ORDERS_SSR_MOCK_PORT || 34895);

export default defineConfig({
  testDir: "./tests/ssr",
  testMatch: "**/*.spec.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results/ssr",
  use: {
    baseURL: `http://127.0.0.1:${appPort}`,
    browserName: "chromium",
    headless: true,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/visual/mockBackend.mjs",
      port: backendPort,
      reuseExistingServer: false,
      timeout: 30_000,
      env: { MOCK_PORT: String(backendPort) },
    },
    {
      command: "node .output/server/index.mjs",
      port: appPort,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: `http://127.0.0.1:${backendPort}`,
        NUXT_PUBLIC_DJANGO_BASE_URL: `http://127.0.0.1:${backendPort}`,
        HOST: "127.0.0.1",
        PORT: String(appPort),
      },
    },
  ],
});
