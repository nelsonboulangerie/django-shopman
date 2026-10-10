import { defineConfig, devices } from "@playwright/test";

// TRAVA DE GEOMETRIA DA VENDA (dono, 10/10): a comanda de altura inteira, sem texto
// cortado e sem sobreposição nas quatro resoluções de mesa e notebook. Sem retrato
// de pixel: o que se prova é a geometria, que não depende da versão do navegador, e
// por isso roda na CI com o Chromium que estiver lá. Backend hermético (o mock das
// fotos, no cenário da venda) e o app em modo cliente, como a matriz visual.
const appPort = Number(process.env.POS_GEOMETRY_PORT || 33032);
const backendPort = Number(process.env.POS_GEOMETRY_MOCK_PORT || 38812);

export default defineConfig({
  testDir: "./tests/geometry",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results/geometry",
  // O primeiro teste paga a compilação do `nuxt dev` a frio.
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${appPort}`,
    bypassCSP: true,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/visual/mockBackend.mjs",
      port: backendPort,
      reuseExistingServer: false,
      timeout: 30_000,
      env: { MOCK_PORT: String(backendPort), MOCK_TODAY: "2026-09-29", MOCK_SCENARIO: "sale" },
    },
    {
      command:
        `NUXT_IGNORE_LOCK=1 POS_VISUAL_CLIENT_ONLY=1 NUXT_APP_BASE_URL=/ ` +
        `NUXT_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
        `NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
        `npx nuxt dev --host 127.0.0.1 --port ${appPort}`,
      url: `http://127.0.0.1:${appPort}/`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
