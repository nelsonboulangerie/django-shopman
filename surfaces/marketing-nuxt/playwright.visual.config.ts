import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// As variáveis existem para quem roda em paralelo numa faixa de portas própria.
const appPort = Number(process.env.MARKETING_VISUAL_APP_PORT || 3010);
const backendPort = Number(process.env.MARKETING_VISUAL_BACKEND_PORT || 9011);

export default defineOperatorVisualConfig({
  app: "marketing-nuxt",
  matrix: false,
  testDir: "./tests/visual",
  outputDir: "./test-results/visual",
  snapshotPathTemplate: "{testDir}/baselines/{arg}{ext}",
  webServer: [
    {
      command: `python3 tests/visual/mock_backend.py ${backendPort}`,
      name: "backend hermético",
      wait: { stdout: new RegExp(`marketing visual mock listening on ${backendPort}`) },
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
    bypassCSP: true,
    viewport: { width: 390, height: 844 },
  },
});
