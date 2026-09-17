import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildOperatorManifest } from "../server/utils/pwa";
import { operatorAppName, windowTitle } from "../app/presentation/windowTitle";
import type { OperatorPwaCapabilityOptions } from "../pwa.config";

// Varredura do NOME dos apps de operador instalados ("Nelson · PDV").
//
// Três regras que o dono pediu e que quebram em silêncio:
//   1. a casa ("Nelson") vem do `Shop.short_name`, nunca do código — o app declara só
//      o rótulo;
//   2. a barra da janela nunca mostra hífen — o separador é o ponto médio;
//   3. o título da janela COMEÇA com o `name` do manifesto, senão o Chrome prefixa
//      `"<name> - "` e o hífen volta por fora.
// Storefront fica fora (é "Nelson Boulangerie", superfície de cliente).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APPS = [
  "hub-nuxt", "pos-nuxt", "kds-nuxt", "orders-nuxt",
  "production-nuxt", "marketing-nuxt", "purchase-nuxt", "bi-nuxt",
] as const;
const HYPHEN_SEPARATOR = /\s[-–—|]\s/;

function manifestBlock(app: string): string {
  const config = readFileSync(resolve(surfacesDir, app, "nuxt.config.ts"), "utf8");
  const start = config.indexOf("manifest: {");
  const end = config.indexOf("icons:", start);
  expect(start, `${app}: definePwaCapability sem manifest`).toBeGreaterThan(-1);
  return config.slice(start, end);
}

function declaredLabel(app: string): string {
  const match = manifestBlock(app).match(/\blabel:\s*"([^"]+)"/);
  expect(match, `${app}: manifest precisa declarar label`).not.toBeNull();
  return match![1];
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(vue|ts)$/.test(entry) ? [path] : [];
  });
}

describe.each(OPERATOR_APPS)("nome instalado de %s", (app) => {
  it("declara só o rótulo: sem name/shortName fixos e sem a casa no código", () => {
    const block = manifestBlock(app);
    expect(block).not.toMatch(/\bname:\s*"/);
    expect(block).not.toMatch(/\bshortName:\s*"/);
    const label = declaredLabel(app);
    expect(label).not.toMatch(HYPHEN_SEPARATOR);
    expect(label).not.toMatch(/Nelson|Shopman|·/i);
  });

  it("o título da janela começa exatamente com o name do manifesto e não tem hífen", () => {
    const label = declaredLabel(app);
    const appName = operatorAppName("Nelson", label);
    const manifest = buildOperatorManifest({
      app,
      display: "standalone",
      manifest: { label, description: "", themeColor: "#fff", backgroundColor: "#fff", icons: [] },
    } as OperatorPwaCapabilityOptions, appName);

    expect(manifest.name).toBe(`Nelson · ${label}`);
    for (const page of [undefined, label, "Filipetas", "404 - Page not found | Nuxt"]) {
      const title = windowTitle(appName, page);
      expect(title.startsWith(manifest.name)).toBe(true);
      expect(title).not.toMatch(HYPHEN_SEPARATOR);
    }
  });

  it("nenhum título escrito no app usa hífen como separador nem escreve document.title cru", () => {
    const offenders = sourceFiles(resolve(surfacesDir, app, "app")).flatMap((file) => {
      const source = readFileSync(file, "utf8");
      const hits: string[] = [];
      for (const match of source.matchAll(/\btitle:\s*(["'`])([^"'`]*)\1/g)) {
        if (HYPHEN_SEPARATOR.test(match[2]) || /^Shopman\b/.test(match[2])) hits.push(`${file}: ${match[0]}`);
      }
      // Escrita direta no título só passa montada por `windowTitle(...)` ou restaurando
      // um valor guardado (`document.title = baseTitle`).
      for (const match of source.matchAll(/document\.title\s*=\s*([^;]+);/g)) {
        const value = match[1].trim();
        if (!/^\w+$/.test(value) && !value.includes("windowTitle(")) hits.push(`${file}: ${match[0]}`);
      }
      return hits;
    });
    expect(offenders).toEqual([]);
  });

  it("a head estática do app é o próprio rótulo (a home não vira 'Casa · App · App')", () => {
    const config = readFileSync(resolve(surfacesDir, app, "nuxt.config.ts"), "utf8");
    const head = config.slice(config.indexOf("head: {"));
    expect(head.match(/\btitle:\s*"([^"]+)"/)?.[1]).toBe(declaredLabel(app));
  });
});
