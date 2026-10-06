import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// Matriz visual do Gestor. Backend hermético (fixtures do seed, sem Django) e o
// app em modo client-only (sem SSR), como POS e Marketing. O runner do ledger
// (scripts/run_operator_visual.py) executa este config por rota/cenário/viewport.

const appPort = 33014;
const backendPort = 38793;

export default defineOperatorVisualConfig({
  app: "orders",
  matrix: false,
  testDir: "./tests/visual",
  outputDir: "./test-results/visual",
  snapshotPathTemplate: "{testDir}/baselines/{arg}{ext}",
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
        "NUXT_IGNORE_LOCK=1 ORDERS_VISUAL_CLIENT_ONLY=1 NUXT_APP_BASE_URL=/ " +
        "NUXT_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
        "NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
        "npx nuxt dev --host 127.0.0.1 --port " + appPort,
      url: "http://127.0.0.1:" + appPort + "/",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:" + appPort,
    bypassCSP: true,
  },
});
