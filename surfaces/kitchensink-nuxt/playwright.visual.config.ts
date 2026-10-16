import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// A porta aceita variável para quem roda em paralelo numa faixa própria.
const port = Number(process.env.KITCHENSINK_VISUAL_PORT || 33114);

export default defineOperatorVisualConfig({
  app: "kitchensink",
  testDir: "./tests/visual",
  webServer: {
    command:
      `KITCHENSINK_VISUAL_MATRIX=1 SHOPMAN_ENVIRONMENT=test ` +
      `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 ` +
      `NUXT_DJANGO_BASE_URL=http://127.0.0.1:1 npx nuxt build && ` +
      `HOST=127.0.0.1 PORT=${port} SHOPMAN_ENVIRONMENT=test ` +
      `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 ` +
      `NUXT_DJANGO_BASE_URL=http://127.0.0.1:1 node .output/server/index.mjs`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
    timeout: 420_000,
  },
  use: { baseURL: `http://127.0.0.1:${port}` },
});
