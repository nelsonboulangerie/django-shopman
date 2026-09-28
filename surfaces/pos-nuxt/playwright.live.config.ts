import { defineConfig, devices } from "@playwright/test";

// Sonda AO VIVO do PDV: contra um PDV de verdade (Django semeado + pos-nuxt),
// não contra o mock. É onde mora a sonda de texto cortado — ela precisa das
// telas cheias (comanda com itens, encomenda com cliente/entrega/data, bloqueios
// do pagamento), e isso o mock não tem. Como rodar: tests/e2e-live/README.md.
export default defineConfig({
  testDir: "./tests/e2e-live",
  testMatch: "**/*.live.spec.ts",
  timeout: 600_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PDV_LIVE_URL || "http://127.0.0.1:3002",
    trace: "retain-on-failure",
    actionTimeout: 15_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
