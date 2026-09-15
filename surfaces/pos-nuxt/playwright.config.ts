import { defineConfig, devices } from "@playwright/test";

// E2E do POS (backend-independente). Sobe um mock backend leve + o app (build de
// produção servido em baseURL '/') para exercitar comportamentos que NÃO dependem de
// dados de negócio: gate de login (sessão de operador ausente → terminal 401) e banner
// offline. Fluxos com dados ricos (comanda→pagamento→cozinha, lock screen, re-gate de
// 401 no meio da sessão) rodam contra o Django real (reviewer local) — ver tests/e2e/README.
const posPort = Number(process.env.POS_E2E_PORT || 3002);
const mockPort = Number(process.env.POS_E2E_MOCK_PORT || 8798);
// O buildDir precisa continuar sob o root do Nuxt para o compiler-sfc resolver
// os tipos do node_modules. O sufixo da porta mantém execuções concorrentes
// independentes sem mover os artefatos para fora do checkout.
const nuxtBuildDir = `.nuxt-e2e-${posPort}`;
const nitroOutputDir = `.output-e2e-${posPort}`;
const serverEntry = `${nitroOutputDir}/server/index.mjs`;

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${posPort}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/e2e/mockBackend.mjs",
      port: mockPort,
      reuseExistingServer: false,
      env: { MOCK_PORT: String(mockPort) },
    },
    {
      // Build com baseURL '/' (produção usa '/pos/') + serve o Nitro. Cada
      // ensaio possui seus processos; porta ocupada exige outro par explícito.
      command: `nuxt build && node ${JSON.stringify(serverEntry)}`,
      port: posPort,
      reuseExistingServer: false,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: `http://127.0.0.1:${mockPort}`,
        NUXT_BUILD_DIR: nuxtBuildDir,
        NITRO_OUTPUT_DIR: nitroOutputDir,
        HOST: "127.0.0.1",
        PORT: String(posPort),
      },
    },
  ],
});
