// Trava das siglas de engenheiro na tela da Produção (WP-F18, P2-04).
//
// "OP" (ordem de produção) e "QC" (controle de qualidade) eram a língua do
// código chegando à tela: o lote se chama Lote, e a etapa que classifica se
// chama Finalização (a revisão do gestor é a Qualidade). A trava olha o que a
// pessoa LÊ (strings e o texto dos templates); comentário de código fica fora,
// porque ADR e plano citam essas siglas como história.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");
const SKIP_DIRS = new Set(["generated", "node_modules", ".nuxt", ".output"]);

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    if (SKIP_DIRS.has(name)) return [];
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(vue|ts)$/.test(name) ? [path] : [];
  });
}

/** O fonte sem comentários, com as linhas no lugar (o número da linha segue valendo). */
export function withoutComments(source: string): string {
  const blank = (match: string) => match.replace(/[^\n]/g, " ");
  return source
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, (match, lead: string) => lead + blank(match.slice(lead.length)));
}

const FORBIDDEN: Array<{ word: RegExp; why: string }> = [
  { word: /\bOP\b/, why: "Lote" },
  { word: /\bQC\b/, why: "Finalização (a etapa) ou Qualidade (a revisão)" },
];

describe("siglas de engenheiro fora da tela da Produção", () => {
  const sources = ["app", "server"].flatMap((dir) => {
    try {
      return files(join(ROOT, dir));
    } catch {
      return [];
    }
  });

  it("varre os fontes do app", () => {
    expect(sources.length).toBeGreaterThan(50);
  });

  it("ignora comentário, mas não string", () => {
    expect(withoutComments('// o QC antigo\nconst t = "QC e timer";')).toMatch(/"QC e timer"/);
    expect(withoutComments("// o QC antigo")).not.toMatch(/QC/);
    expect(withoutComments("<!-- Histórico por OP -->")).not.toMatch(/OP/);
  });

  for (const { word, why } of FORBIDDEN) {
    it(`não mostra ${word} (a palavra é: ${why})`, () => {
      const hits = sources.flatMap((path) =>
        withoutComments(readFileSync(path, "utf8"))
          .split("\n")
          .map((line, index) => ({ line, index }))
          .filter(({ line }) => word.test(line))
          .map(({ index }) => `${relative(ROOT, path)}:${index + 1}`),
      );
      expect(hits).toEqual([]);
    });
  }
});
