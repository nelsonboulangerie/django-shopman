import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// Um único harness para comportamento, acessibilidade, geometria e assinaturas.
// A seleção da suíte pertence aos scripts do contrato; boot, relógio, browser,
// locale, retry e artefato publicado pertencem a esta fábrica compartilhada.
const appPort = Number(process.env.MARKETING_BROWSER_APP_PORT || 3010);
const backendPort = Number(process.env.MARKETING_BROWSER_BACKEND_PORT || 9011);
const managed = process.env.MARKETING_E2E_MANAGED !== "0";

const visualEnvironment =
  `MARKETING_VISUAL_CLIENT_ONLY=1 MARKETING_VISUAL_MATRIX=1 ` +
  `NUXT_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
  `NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:${backendPort}`;

export default defineOperatorVisualConfig({
  app: "marketing",
  matrix: false,
  testDir: "./tests",
  outputDir: "./test-results/browser",
  snapshotPathTemplate: "{testDir}/visual/baselines/{arg}{ext}",
  webServer: managed
    ? [
        {
          command: `python3 tests/visual/mock_backend.py ${backendPort}`,
          name: "backend hermético",
          wait: { stdout: new RegExp(`marketing visual mock listening on ${backendPort}`) },
          reuseExistingServer: false,
          timeout: 30_000,
        },
        {
          command:
            `${visualEnvironment} SHOPMAN_ENVIRONMENT=test ` +
            `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 npx nuxt build && ` +
            `HOST=127.0.0.1 PORT=${appPort} ` +
            `NUXT_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
            `SHOPMAN_ENVIRONMENT=test SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 ` +
            `node .output/server/index.mjs`,
          url: `http://127.0.0.1:${appPort}/`,
          reuseExistingServer: false,
          timeout: 420_000,
        },
      ]
    : undefined,
  use: {
    baseURL: process.env.MARKETING_E2E_BASE_URL ?? `http://127.0.0.1:${appPort}`,
    bypassCSP: true,
    viewport: { width: 390, height: 844 },
  },
});
