import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

// Suíte de operador de verdade (WP-G00): o Gestor COMPILADO contra o Django de uma pilha
// já de pé, com login, PIN e pedido nascido pela loja. Como subir a pilha:
// tests/operator/README.md. Sem a pilha declarada, a suíte recusa rodar: um teste que
// "passa" contra o Django errado (ou contra nenhum) não prova nada.
const required = {
  OPERATOR_DJANGO_URL: "o Django da pilha (ex.: http://127.0.0.1:8062)",
  OPERATOR_STORE_URL: "a loja compilada da pilha (ex.: http://127.0.0.1:3180)",
  OPERATOR_KITCHEN_URL: "a Cozinha compilada da pilha (ex.: http://127.0.0.1:3183)",
  OPERATOR_DJANGO_LOG: "o arquivo onde o runserver da pilha escreve (o código de entrada da loja sai nele)",
} as const;
const missing = Object.entries(required).filter(([name]) => !process.env[name]);
if (missing.length) {
  throw new Error(
    "Suba a pilha de operador antes desta suíte (tests/operator/README.md). Faltam:\n"
      + missing.map(([name, what]) => `  ${name}: ${what}`).join("\n"),
  );
}
if (!existsSync(new URL("./.output/server/index.mjs", import.meta.url))) {
  throw new Error("Compile o Gestor antes (npx nuxt build): a suíte sobe .output/server/index.mjs.");
}

const django = process.env.OPERATOR_DJANGO_URL!.replace(/\/$/, "");
const port = Number(process.env.OPERATOR_GESTOR_PORT || 3184);

export default defineConfig({
  testDir: "./tests/operator",
  testMatch: "**/*.spec.ts",
  // Uma jornada inteira (loja, Gestor e Cozinha) numa pilha local. A máquina de quem
  // roda costuma estar carregada; o tempo aqui é de jornada, não de clique.
  timeout: 900_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results/operator",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 60_000,
    navigationTimeout: 60_000,
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
      HOST: "127.0.0.1",
      PORT: String(port),
    },
  },
});
