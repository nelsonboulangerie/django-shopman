import { readdirSync, readFileSync } from "node:fs";
import { extname } from "node:path";
import { describe, expect, it } from "vitest";

// F8 do laudo do Gestor (P1-6): palavras que o vocabulário fechado da suíte já trocou
// (`docs/reference/suite-vocabulary.md`) e que o Gestor seguia dizendo. Lê o texto de
// tela e as strings do app; comentário não conta (o comentário pode contar a história).
//
//   "Ciente"           → "Visto" (§2.1: reconhecer um aviso é Visto, nos nove apps)
//   "Agendado(s)"      → "Encomenda(s)" (pedido para data futura, §3 e §5)
//   "Falha na ação"    → o nome do gesto que falhou ("Não deu para concluir “Aceitar”")
//   coluna "Etapa"     → "Situação" (etapa é da receita, §1; o Histórico já diz Situação)

const root = new URL("../app/", import.meta.url);

function files(path: URL): URL[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(`${entry.name}${entry.isDirectory() ? "/" : ""}`, path);
    if (entry.isDirectory())
      return entry.name === "generated" ? [] : files(child);
    return [".vue", ".ts"].includes(extname(entry.name)) ? [child] : [];
  });
}

/** O arquivo sem comentários: `// …`, `/* … *\/` e `<!-- … -->`. */
function withoutComments(source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

const RETIRED: Array<[string, RegExp]> = [
  ["Ciente", /\bCiente\b/],
  ["Agendado", /\bAgendad[oa]s?\b/],
  ["Falha na ação", /Falha na ação/],
  ['"Etapa" como coluna', /["'`]Etapa["'`]/],
];

describe("vocabulário fechado no Gestor (F8 do laudo)", () => {
  const sources = files(root).map((file) => ({
    file: file.pathname.split("/app/").pop() ?? file.pathname,
    code: withoutComments(readFileSync(file, "utf8")),
  }));

  it.each(RETIRED)("nenhum texto do app diz %s", (_word, pattern) => {
    expect(
      sources.filter(({ code }) => pattern.test(code)).map(({ file }) => file),
    ).toEqual([]);
  });

  it("a trava enxerga o app inteiro", () => {
    expect(sources.length).toBeGreaterThan(80);
  });
});
