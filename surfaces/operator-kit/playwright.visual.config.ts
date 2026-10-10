import { defineOperatorVisualConfig } from "./visual/playwright";

// A porta aceita variável para quem roda em paralelo numa faixa própria.
const port = Number(process.env.OPERATOR_KIT_CATALOG_PORT || 33113);

export default defineOperatorVisualConfig({
  app: "operator-kit",
  testDir: "./tests/catalog",
  webServer: {
    command: `OPERATOR_KIT_CATALOG=1 npx nuxt dev --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/__operator_kit_catalog`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  use: { baseURL: `http://127.0.0.1:${port}` },
});
