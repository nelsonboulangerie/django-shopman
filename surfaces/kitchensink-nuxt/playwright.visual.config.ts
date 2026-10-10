import { defineOperatorVisualConfig } from "../operator-kit/visual/playwright";

// A porta aceita variável para quem roda em paralelo numa faixa própria.
const port = Number(process.env.KITCHENSINK_VISUAL_PORT || 33114);

export default defineOperatorVisualConfig({
  app: "kitchensink",
  testDir: "./tests/visual",
  webServer: {
    command: `KITCHENSINK_VISUAL_MATRIX=1 npx nuxt dev --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: process.env.CI !== "true",
    timeout: 120_000,
  },
  use: { baseURL: `http://127.0.0.1:${port}` },
});
