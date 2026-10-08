import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// Matriz visual do B.I. Backend hermético (leituras GRAVADAS do Django com o seed,
// sem Django vivo) e o app com SSR, como roda no ar: o B.I. não tem modo client-only.
// Portas próprias para não colidir com a matriz do Gestor (33014/38793).
// Procedimento de regravação das fixtures: tests/visual/README.md.

const appPort = 33017;
const backendPort = 38794;

export default defineOperatorVisualConfig({
  app: "bi",
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
        "NUXT_IGNORE_LOCK=1 NUXT_APP_BASE_URL=/ " +
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
