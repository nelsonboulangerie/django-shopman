import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// Matriz visual da Cozinha (fase 2). Backend hermético: o mock de prévia
// (`KDS_MOCK_FIXTURE=preview`, os quadros de `tests/e2e/previewFixtures.mjs`) e o app
// no build de produção com SSR, como roda no ar, para pegar o desenho da carga direta
// (o celular não pode nascer com o quadro da mesa). Portas próprias, fora das do e2e
// (3103/8798), da prévia (3013/8799) e das matrizes do Gestor e do B.I.
// Sem baseline de retrato: o retrato só se grava com o browser da CI
// (docs/reference/operator-visual-baselines.md). O spec anexa as capturas ao relatório.

// As variáveis existem para quem roda em paralelo numa faixa de portas própria.
const appPort = Number(process.env.KDS_VISUAL_APP_PORT || 33019);
const backendPort = Number(process.env.KDS_VISUAL_BACKEND_PORT || 38797);

export default defineOperatorVisualConfig({
  app: "kds",
  matrix: false,
  testDir: "./tests/visual",
  outputDir: "./test-results/visual",
  snapshotPathTemplate: "{testDir}/baselines/{arg}{ext}",
  webServer: [
    {
      command: "node tests/e2e/mockBackend.mjs",
      port: backendPort,
      reuseExistingServer: false,
      timeout: 30_000,
      env: { MOCK_PORT: String(backendPort), KDS_MOCK_FIXTURE: "preview" },
    },
    {
      command: "nuxt build && node .output/server/index.mjs",
      url: "http://127.0.0.1:" + appPort + "/pickup",
      reuseExistingServer: false,
      timeout: 300_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:" + backendPort,
        HOST: "127.0.0.1",
        PORT: String(appPort),
      },
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:" + appPort,
  },
});
