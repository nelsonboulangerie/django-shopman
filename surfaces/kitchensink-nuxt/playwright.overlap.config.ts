import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// A trava da sobreposição do catálogo: mesmo servidor do retrato (build de produção, sem
// backend), mas sem a matriz visual e sem o reporter de evidência. O globalSetup do kit
// fica: ele só confere que o Chromium é o travado, e geometria medida em outro navegador
// não vale como prova.
const port = Number(process.env.KITCHENSINK_OVERLAP_PORT || 41009);
// Quem já tem o `.output` deste mesmo build (o mesmo env abaixo) pula a compilação com
// KITCHENSINK_OVERLAP_PREBUILT=1: numa máquina carregada o build passa dos 7 minutos.
const build =
  process.env.KITCHENSINK_OVERLAP_PREBUILT === "1"
    ? ""
    : `KITCHENSINK_VISUAL_MATRIX=1 SHOPMAN_ENVIRONMENT=test ` +
      `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 ` +
      `NUXT_DJANGO_BASE_URL=http://127.0.0.1:1 npx nuxt build && `;

export default defineConfig({
  testDir: "./tests/overlap",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results/operator-overlap",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 45_000 },
  globalSetup: join(
    import.meta.dirname,
    "../operator-kit/visual/globalSetup.ts",
  ),
  reporter: [["list"]],
  webServer: {
    command:
      build +
      `HOST=127.0.0.1 PORT=${port} SHOPMAN_ENVIRONMENT=test ` +
      `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 ` +
      `NUXT_DJANGO_BASE_URL=http://127.0.0.1:1 node .output/server/index.mjs`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
    timeout: 420_000,
  },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: "chromium",
    headless: true,
    colorScheme: "light",
    locale: "pt-BR",
    reducedMotion: "reduce",
    serviceWorkers: "block",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
  },
});
