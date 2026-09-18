import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildOperatorManifest } from "../server/utils/pwa";
import { operatorAppName, windowTitle } from "../app/presentation/windowTitle";
import { resolveOperatorPwa } from "../pwa.config";
import { OPERATOR_APPS, OPERATOR_CANVAS, type OperatorAppRef } from "../appIdentity";

// Varredura do NOME e da COR dos apps de operador instalados ("Nelson · PDV").
//
// Quatro regras que o dono pediu e que quebram em silêncio:
//   1. a casa ("Nelson") vem do `Shop.short_name`, nunca do código — o app declara só
//      o rótulo, e num lugar só (`app-identity.json`);
//   2. a barra da janela nunca mostra hífen — o separador é o ponto médio;
//   3. o título da janela COMEÇA com o `name` do manifesto, senão o Chrome prefixa
//      `"<name> - "` e o hífen volta por fora;
//   4. a barra de título do app instalado é a cor do ÍCONE. Eram oito barras sem
//      relação com o ícone no Mac, porque a cor estava escrita em três lugares.
// Storefront fica fora (é "Nelson Boulangerie", superfície de cliente).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APP_REFS = Object.keys(OPERATOR_APPS) as OperatorAppRef[];
const HYPHEN_SEPARATOR = /\s[-–—|]\s/;

function config(app: OperatorAppRef): string {
  return readFileSync(resolve(surfacesDir, `${app}-nuxt`, "nuxt.config.ts"), "utf8");
}

/** Comentário citando o caminho do ícone é prosa, não call site: sai antes da varredura. */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/[^\n]*/g, "$1");
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(vue|ts)$/.test(entry) ? [path] : [];
  });
}

describe.each(OPERATOR_APP_REFS)("nome instalado de %s", (app) => {
  const identity = OPERATOR_APPS[app];
  const resolved = resolveOperatorPwa({ app, display: "standalone" });

  it("o rótulo é só o app: sem a casa, sem marca e sem separador", () => {
    expect(identity.label).not.toMatch(HYPHEN_SEPARATOR);
    expect(identity.label).not.toMatch(/Nelson|Shopman|·/i);
    expect(identity.label.trim()).toBe(identity.label);
    expect(identity.description).not.toMatch(/Nelson|Shopman/i);
  });

  it("o nuxt.config não reescreve rótulo, descrição, cor nem ícone", () => {
    const source = config(app);
    expect(source).toContain("definePwaCapability(");
    for (const rewritten of [/\blabel:/, /\bdescription:/, /\bthemeColor:/, /\bbackgroundColor:/, /\bicons:/]) {
      expect(source, `${app}: a identidade voltou para o nuxt.config`).not.toMatch(rewritten);
    }
    // `title` e `theme-color` do `<head>` também saem da capability: com os dois
    // escritos, o do app perdia em silêncio e ninguém via a cor morta (a Central
    // declarava `#fafafa` e servia `#7C3A40`).
    expect(source).not.toMatch(/\btitle:\s*["']/);
    expect(source).not.toMatch(/name:\s*["']theme-color["']/);
  });

  it("o título da janela começa exatamente com o name do manifesto e não tem hífen", () => {
    const appName = operatorAppName("Nelson", identity.label);
    const manifest = buildOperatorManifest(resolved, appName);

    expect(manifest.name).toBe(`Nelson · ${identity.label}`);
    expect(manifest.short_name).toBe(identity.label);
    for (const page of [undefined, identity.label, "Filipetas", "404 - Page not found | Nuxt"]) {
      const title = windowTitle(appName, page);
      expect(title.startsWith(manifest.name)).toBe(true);
      expect(title).not.toMatch(HYPHEN_SEPARATOR);
    }
  });

  it("a barra de título do app instalado é a cor do ícone", () => {
    const manifest = buildOperatorManifest(resolved);
    expect(manifest.theme_color).toBe(identity.color);
    // A tela de abertura é o `--background` do tema do operador, não uma cor avulsa:
    // cinco apps piscavam `#FAFAF9` e a Cozinha `#0A0A0A`, cores que nenhuma tela usa.
    expect(manifest.background_color).toBe(identity.dark ? OPERATOR_CANVAS.dark : OPERATOR_CANVAS.light);
  });

  it("nenhum título escrito no app usa hífen como separador nem escreve document.title cru", () => {
    const offenders = sourceFiles(resolve(surfacesDir, `${app}-nuxt`, "app")).flatMap((file) => {
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

  it("o app não reescreve o próprio rótulo nem o caminho do ícone na tela", () => {
    const offenders = sourceFiles(resolve(surfacesDir, `${app}-nuxt`, "app")).flatMap((file) => {
      const source = withoutComments(readFileSync(file, "utf8"));
      const hits: string[] = [];
      // Rail, gate de login e título herdam a identidade pelo `runtimeConfig`. Escrever
      // o rótulo aqui foi como a Cozinha virou "KDS" na janela e "Cozinha" no rail.
      if (/app-label=|:app-label=/.test(source)) hits.push(`${file}: app-label`);
      if (/useOperatorWindowTitle\(\s*["'`]/.test(source)) hits.push(`${file}: rótulo no título`);
      if (/useOperatorAppName\(\s*["'`]/.test(source)) hits.push(`${file}: rótulo no nome do app`);
      if (/["'`]\/pwa\/pwa-\d+x\d+\.png/.test(source)) hits.push(`${file}: caminho do ícone`);
      return hits;
    });
    expect(offenders).toEqual([]);
  });
});

describe("identidade dos apps de operador", () => {
  it("cada app tem a própria cor: duas barras de título iguais não situam ninguém", () => {
    const colors = OPERATOR_APP_REFS.map((app) => OPERATOR_APPS[app].color);
    expect(new Set(colors).size).toBe(colors.length);
  });

  it("cada app tem o próprio rótulo", () => {
    const labels = OPERATOR_APP_REFS.map((app) => OPERATOR_APPS[app].label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("app fora da tabela para o build em vez de publicar manifesto sem nome", () => {
    expect(() => resolveOperatorPwa({ app: "inexistente" as OperatorAppRef, display: "standalone" }))
      .toThrow(/app de operador desconhecido/);
  });
});
