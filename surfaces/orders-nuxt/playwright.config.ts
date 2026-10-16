import { defineConfig, devices } from "@playwright/test";

// Portas configuráveis: várias sessões rodam esta suíte ao mesmo tempo, e duas na
// mesma porta reaproveitam o servidor uma da outra (reuseExistingServer).
const APP_PORT = Number(process.env.ORDERS_E2E_PORT || 3004);
const MOCK_PORT = Number(process.env.MOCK_PORT || 8796);

// E2E do Gestor (backend-independente). Mock backend serve uma sessão autenticada + uma
// fila com cards → o board renderiza; + banner offline. Build com baseURL '/', igual à
// produção (o app é servido na raiz do subdomínio). Login efetivo, lock (Opção C) e ações reais rodam contra o Django real
// (reviewer local) — ver tests/e2e/README.
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
      env: { MOCK_PORT: String(MOCK_PORT) },
      port: MOCK_PORT,
      reuseExistingServer: !process.env.CI,
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
