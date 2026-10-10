import { execFileSync } from "node:child_process";

import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// Matriz visual do Gestor. Backend hermético (fixtures do seed, sem Django) e o
// app em modo client-only (sem SSR), como POS e Marketing: a carga direta com SSR é a
// régua do `test:ssr` (`playwright.ssr.config.ts`), não desta. O runner do ledger
// (scripts/run_operator_visual.py) executa este config por rota/cenário/viewport.
//
// Roda o BUILD de produção, não o `nuxt dev`, como as matrizes do Compras e da Cozinha:
// no dev a primeira visita a cada rota otimiza dependências e recarrega a página. O
// `ORDERS_VISUAL_CLIENT_ONLY` vale no build (o `ssr` do `nuxt.config.ts` é de build).
//
// Portas: as variáveis para quem roda numa faixa própria; sem elas, portas livres que
// o sistema dá agora. Ficam gravadas no ambiente para os workers (que releem este
// arquivo) e o spec (`ORDERS_VISUAL_BACKEND_PORT`) acharem as mesmas.

function freePort(): number {
  const out = execFileSync(
    process.execPath,
    [
      "-e",
      "const s=require('node:net').createServer();" +
        "s.listen(0,'127.0.0.1',()=>{process.stdout.write(String(s.address().port));s.close();});",
    ],
    { encoding: "utf8" },
  );
  return Number(out.trim());
}

process.env.ORDERS_VISUAL_APP_PORT ||= String(freePort());
process.env.ORDERS_VISUAL_BACKEND_PORT ||= String(freePort());

const appPort = Number(process.env.ORDERS_VISUAL_APP_PORT);
const backendPort = Number(process.env.ORDERS_VISUAL_BACKEND_PORT);

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
      command: "ORDERS_VISUAL_CLIENT_ONLY=1 npx nuxt build && node .output/server/index.mjs",
      url: "http://127.0.0.1:" + appPort + "/",
      reuseExistingServer: false,
      timeout: 420_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:" + backendPort,
        NUXT_PUBLIC_DJANGO_BASE_URL: "http://127.0.0.1:" + backendPort,
        HOST: "127.0.0.1",
        PORT: String(appPort),
      },
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:" + appPort,
    bypassCSP: true,
  },
});
