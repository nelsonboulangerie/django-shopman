import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

export default defineOperatorVisualConfig({
  app: "kitchensink",
  testDir: "./tests/visual",
  webServer: {
    command: "KITCHENSINK_VISUAL_MATRIX=1 npx nuxt dev --host 127.0.0.1 --port 33114",
    url: "http://127.0.0.1:33114/",
    reuseExistingServer: process.env.CI !== "true",
    timeout: 120_000,
  },
  use: { baseURL: "http://127.0.0.1:33114" },
});
