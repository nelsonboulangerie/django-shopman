import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrail de COBERTURA de lint das superfícies.
//
// A dívida que este arquivo tranca: `eslint .` roda a partir do diretório de cada
// app e nunca alcança `../operator-kit`. Por anos o layer — BFF, composables, 24
// componentes — ditou a base de lint dos nove apps sem nunca passar por ESLint,
// porque ninguém olhava o que FALTAVA: cada app tinha o seu `lint` e o conjunto
// parecia completo. A varredura abaixo lê o diretório `surfaces/` em vez de uma
// lista escrita à mão, para que uma superfície nova nasça linta-da ou vermelha.
const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

// `operator-router` fica de fora, com motivo: é o launcher/roteador por Host dos
// grupos de operador (ADR-030), escrito em `.mjs` puro e declaradamente SEM
// dependências ("só a biblioteca padrão do Node"). Dar ESLint a ele significa dar-lhe
// o primeiro `node_modules`, e isso é decisão própria, não carona deste guardrail.
// Ele segue sem lint: é a lacuna conhecida que sobra depois do operator-kit.
const FORA_DO_LINT = new Set(["operator-router"]);

/** Diretório em `surfaces/` que é um pacote npm de superfície (tem package.json). */
function surfacePackages(): string[] {
  return readdirSync(surfacesDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith("."))
    .map((entry) => entry.name)
    .filter((name) => existsSync(resolve(surfacesDir, name, "package.json")))
    .filter((name) => !FORA_DO_LINT.has(name))
    .sort();
}

function scriptsOf(surface: string): Record<string, string> {
  const raw = readFileSync(resolve(surfacesDir, surface, "package.json"), "utf8");
  return (JSON.parse(raw) as { scripts?: Record<string, string> }).scripts ?? {};
}

/** Flat config próprio: `eslint.config.mjs` na raiz da superfície. */
function hasFlatConfig(surface: string): boolean {
  return existsSync(resolve(surfacesDir, surface, "eslint.config.mjs"));
}

describe("cobertura de lint das superfícies", () => {
  const surfaces = surfacePackages();

  it("acha as superfícies pelo diretório, não por lista escrita à mão", () => {
    expect(surfaces).toContain("operator-kit");
    expect(surfaces.length).toBeGreaterThanOrEqual(10);
  });

  it.each(surfacePackages())("%s tem script `lint`", (surface) => {
    expect(scriptsOf(surface).lint).toBeDefined();
  });

  it.each(surfacePackages())("%s tem flat config próprio", (surface) => {
    expect(hasFlatConfig(surface)).toBe(true);
  });

  it("o kit NÃO parte de `.nuxt/eslint.config.mjs` — layer não registra @nuxt/eslint", () => {
    // `nuxt prepare` roda no layer (gera tipos) mas não escreve config de ESLint:
    // quem escreve é o módulo `@nuxt/eslint`, e o `nuxt.config.ts` do layer não
    // registra módulo nenhum de propósito (módulo daqui vaza por `extends`).
    // Se um dia alguém "uniformizar" o kit copiando o import dos apps, o lint do
    // kit passa a depender de um arquivo que nunca é gerado — e some em silêncio.
    // Olha o IMPORT, não a menção: o próprio config explica em prosa por que não
    // parte do `.nuxt`, e um `toContain` cru se acusaria a si mesmo.
    const config = readFileSync(resolve(surfacesDir, "operator-kit", "eslint.config.mjs"), "utf8");
    const imports = config.split("\n").filter((line) => /^\s*import\s/.test(line));
    expect(imports.some((line) => line.includes(".nuxt/eslint.config.mjs"))).toBe(false);
    expect(config).toContain("./eslint.config.base.mjs");

    const nuxtConfig = readFileSync(resolve(surfacesDir, "operator-kit", "nuxt.config.ts"), "utf8");
    expect(nuxtConfig).not.toContain("modules:");
  });
});
