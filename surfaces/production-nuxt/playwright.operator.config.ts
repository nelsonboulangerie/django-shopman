import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

// Suíte de operador de verdade da Produção (WP-F00): o app COMPILADO contra o Django de
// uma pilha já de pé, com a Gerente entrando com senha, a Cozinha com PIN no teclado da
// tela e a loja de verdade ao lado. Como subir a pilha: tests/operator/README.md. Sem a
// pilha declarada, a suíte recusa rodar: um teste que "passa" contra o Django errado (ou
// contra nenhum) não prova nada. Os e2e de mock (playwright.config.ts) seguem como estão.
const required = {
  OPERATOR_DJANGO_URL: "o Django da pilha (ex.: http://127.0.0.1:8095)",
  OPERATOR_STORE_URL: "a loja compilada da pilha (ex.: http://127.0.0.1:3197)",
} as const;
const missing = Object.entries(required).filter(([name]) => !process.env[name]);
if (missing.length) {
  throw new Error(
    "Suba a pilha de operador antes desta suíte (tests/operator/README.md). Faltam:\n" +
      missing.map(([name, what]) => `  ${name}: ${what}`).join("\n"),
  );
}
if (!existsSync(new URL("./.output/server/index.mjs", import.meta.url))) {
  throw new Error(
    "Compile a Produção antes (tests/operator/README.md, seção "Subir a pilha", item 3): a suíte sobe .output/server/index.mjs.",
  );
}

const django = process.env.OPERATOR_DJANGO_URL!.replace(/\/$/, "");
const port = Number(process.env.OPERATOR_PRODUCTION_PORT || 3196);

export default defineConfig({
  testDir: "./tests/operator",
  testMatch: "**/*.spec.ts",
  // Uma jornada inteira (Produção e loja) numa pilha local. A máquina de quem roda
  // costuma estar carregada; o tempo aqui é de jornada, não de clique.
  timeout: 1_800_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  forbidOnly: true,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results/operator",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 60_000,
    navigationTimeout: 180_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "node .output/server/index.mjs",
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      NUXT_APP_BASE_URL: "/",
      NUXT_DJANGO_BASE_URL: django,
      NUXT_PUBLIC_DJANGO_BASE_URL: django,
      // O envelope estrito da Produção recusa upstream HTTP; a pilha local é a exceção
      // declarada de teste (a mesma dos e2e de mock e da J6 do Gestor).
      NUXT_SHOPMAN_ENVIRONMENT: "test",
      SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM: "1",
      HOST: "127.0.0.1",
      PORT: String(port),
    },
  },
});
