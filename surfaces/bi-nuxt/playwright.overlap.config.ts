import type { PlaywrightTestConfig } from "@playwright/test";

import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// Trava da sobreposição do B.I. (tests/overlap): o mesmo backend hermético da matriz
// visual (leituras GRAVADAS do Django, tests/visual/mockBackend.mjs) e o mesmo build de
// produção com SSR. Herda do kit o globalSetup (só confere o Chromium travado: a
// geometria depende da fonte que ele desenha) e a base de `use`; troca o reporter de
// evidência por `list`, porque aqui não há retrato nem evidência a gravar.
// Portas por env, para várias sessões rodarem ao mesmo tempo sem colidir.

const appPort = Number(process.env.BI_OVERLAP_APP_PORT || 41007);
const backendPort = Number(process.env.BI_OVERLAP_BACKEND_PORT || 41807);

// BI_OVERLAP_PREBUILT=1 serve o `.output` já construído (com o mesmo upstream de teste),
// para repetir a trava depois de um build sem pagar outro.
const build =
  process.env.BI_OVERLAP_PREBUILT === "1"
    ? ""
    : "NUXT_APP_BASE_URL=/ " +
      "NUXT_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
      "NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
      "SHOPMAN_ENVIRONMENT=test SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 " +
      "npx nuxt build && ";

const visual = defineOperatorVisualConfig({
  app: "bi",
  matrix: false,
  testDir: "./tests/overlap",
  outputDir: "./test-results/overlap",
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
        build +
        "HOST=127.0.0.1 PORT=" + appPort + " " +
        "NUXT_DJANGO_BASE_URL=http://127.0.0.1:" + backendPort + " " +
        "SHOPMAN_ENVIRONMENT=test SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 " +
        "node .output/server/index.mjs",
      url: "http://127.0.0.1:" + appPort + "/",
      reuseExistingServer: false,
      // O build de produção leva minutos, e mais quando outros apps constroem junto.
      timeout: 900_000,
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:" + appPort,
    bypassCSP: true,
  },
});

const config: PlaywrightTestConfig = { ...visual, reporter: [["list"]] };

export default config;
