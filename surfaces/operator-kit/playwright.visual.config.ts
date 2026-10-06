import { defineOperatorVisualConfig } from "./visual/playwright";

export default defineOperatorVisualConfig({
  app: "operator-kit",
  testDir: "./tests/catalog",
  webServer: {
    command: "OPERATOR_KIT_CATALOG=1 npx nuxt dev --host 127.0.0.1 --port 33113",
    url: "http://127.0.0.1:33113/__operator_kit_catalog",
    reuseExistingServer: false,
    timeout: 120_000,
  },
  use: { baseURL: "http://127.0.0.1:33113" },
});
