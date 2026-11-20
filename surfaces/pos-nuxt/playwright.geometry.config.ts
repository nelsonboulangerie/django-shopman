import { defineConfig, devices } from "@playwright/test";

// TRAVA DE GEOMETRIA DA VENDA (dono, 10/10): a comanda de altura inteira, sem texto
// cortado e sem sobreposição nas quatro resoluções de mesa e notebook. Sem retrato
// de pixel: o que se prova é a geometria, e por isso roda na CI em Linux.
//
// A MÉTRICA DA FONTE, SIM, depende do SO (medido em 18/11/2026, #2651): o Chromium
// headless do Linux aplica hinting cheio, que arredonda o avanço de cada glifo para
// cima, e "Roberto Albuquerque" media 153 px no Linux contra <= 150 px no macOS. O
// Chrome de mesa do macOS desenha sem esse arredondamento, e é nele que o contrato
// foi calibrado. `--font-render-hinting=none` desliga o hinting no headless; o
// contrato (nada corta, nada se sobrepõe) não muda. A folga do nome no cabeçalho é
// pequena mesmo no macOS: ver #2650. Backend hermético (o mock das
// fotos, no cenário da venda) e o app em modo cliente, como a matriz visual.
const appPort = Number(process.env.POS_GEOMETRY_PORT || 33032);
const backendPort = Number(process.env.POS_GEOMETRY_MOCK_PORT || 38812);

export default defineConfig({
  testDir: "./tests/geometry",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results/geometry",
  // O primeiro teste paga a compilação do `nuxt dev` a frio.
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${appPort}`,
    bypassCSP: true,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], launchOptions: { args: ["--font-render-hinting=none"] } } }],
  webServer: [
    {
      command: "node tests/visual/mockBackend.mjs",
      port: backendPort,
      reuseExistingServer: false,
      timeout: 30_000,
      // `MOCK_ADDRESS`: a comanda 12 abre como encomenda com entrega, para a trava do
      // endereço (`deliveryAddress.spec.ts`); a 13, da trava da comanda, não muda.
      // `MOCK_CUSTOMER`: a busca de cliente acha a Maria Santos, com o diálogo Cliente
      // cheio, para a trava do transbordo a 375 px (`customerModal.spec.ts`, #2885).
      env: { MOCK_PORT: String(backendPort), MOCK_TODAY: "2026-09-29", MOCK_SCENARIO: "sale", MOCK_ADDRESS: "1", MOCK_CUSTOMER: "1" },
    },
    {
      command:
        `NUXT_IGNORE_LOCK=1 POS_VISUAL_CLIENT_ONLY=1 NUXT_APP_BASE_URL=/ ` +
        `NUXT_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
        `NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:${backendPort} ` +
        `npx nuxt dev --host 127.0.0.1 --port ${appPort}`,
      url: `http://127.0.0.1:${appPort}/`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
