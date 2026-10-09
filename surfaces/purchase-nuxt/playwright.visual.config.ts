import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// Matriz visual do Compras (fase 2), no molde do Gestor: backend hermético
// (`tests/visual/mockBackend.mjs`, cadastro sintético) e o app client-only (o Compras já
// é `ssr: false`). Roda o BUILD de produção, não o `nuxt dev`: no dev a primeira visita a
// cada rota otimiza dependências e recarrega a página, e a captura saía em branco.
// O runner do ledger (scripts/run_operator_visual.py) executa este config por rota/cenário/viewport. Sem baseline de pixel: o gate é o scanner de
// geometria do kit (`captureOperatorEvidence`). Baseline, se um dia houver, só pela CI.

const appPort = Number(process.env.PURCHASE_VISUAL_APP_PORT || 35020);
const backendPort = Number(process.env.PURCHASE_VISUAL_BACKEND_PORT || 35021);

export default defineOperatorVisualConfig({
  app: "purchase",
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
        "npx nuxt build && " +
        "HOST=127.0.0.1 PORT=" + appPort + " " +
        "NUXT_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
        "NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
        "node .output/server/index.mjs",
      url: "http://127.0.0.1:" + appPort + "/",
      reuseExistingServer: false,
      timeout: 420_000,
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:" + appPort,
    bypassCSP: true,
  },
});
