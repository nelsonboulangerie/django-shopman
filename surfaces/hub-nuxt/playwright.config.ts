import { defineConfig, devices } from "@playwright/test";

// E2E da Central (backend-independente). Mock backend serve uma projection de hub com
// tiles → o app renderiza o launcher; + banner offline. Build com baseURL '/' (produção
// usa '/central/'). Fluxo com Django real (login efetivo, permissões) = reviewer local.
// Portas configuráveis por env (HUB_E2E_APP_PORT / HUB_E2E_MOCK_PORT) para rodar ao lado
// de outros apps sem colidir; os defaults são os de sempre.
const APP_PORT = Number(process.env.HUB_E2E_APP_PORT || 3001);
const MOCK_PORT = Number(process.env.HUB_E2E_MOCK_PORT || 8797);

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${APP_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/e2e/mockBackend.mjs",
      port: MOCK_PORT,
      reuseExistingServer: !process.env.CI,
      env: { MOCK_PORT: String(MOCK_PORT) },
    },
    {
      command: "nuxt build && node .output/server/index.mjs",
      port: APP_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: `http://127.0.0.1:${MOCK_PORT}`,
        HOST: "127.0.0.1",
        PORT: String(APP_PORT),
      },
    },
  ],
});
