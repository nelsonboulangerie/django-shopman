import { readdirSync, readFileSync } from "node:fs";
import { extname } from "node:path";
import { describe, expect, it } from "vitest";

// Marketing canônico em Nuxt UI (fase 2, WP-FASE2-UX-OPERADOR, onda do Marketing): a
// mesma trava do Gestor (`orders-nuxt/tests/canonicalPilot.guardrails.test.ts`), sobre
// o que o Marketing escreve em `app/`. O que entrou aqui não volta:
//   - nenhum controle HTML cru (botão, campo, lista, formulário, tabela);
//   - nenhum `<Ui…>` do kit antigo, exceto os cinco campos de data e hora, que são o
//     cânone da suíte por decisão do dono (camadas finas sobre InputDate/InputTime);
//   - nenhum `:ui` por instância (o desenho mora no tema ou na peça do kit);
//   - nenhum tamanho de texto arbitrário (`text-[13px]`): cinco tamanhos, os do conjunto;
//   - nenhuma barra grudada na base feita à mão (a ação na base é o `OperatorActionBar`);
//   - nenhuma régua de largura em JS (`useMediaQuery` de largura): a régua é a do CSS.

const appRoot = new URL("../app/", import.meta.url);

function vueFiles(path = appRoot): URL[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(`${entry.name}${entry.isDirectory() ? "/" : ""}`, path);
    if (entry.isDirectory()) return vueFiles(child);
    return extname(entry.name) === ".vue" ? [child] : [];
  });
}

const sources = vueFiles().map((url) => ({
  file: url.pathname.split("/app/")[1],
  source: readFileSync(url, "utf8"),
}));

function templateOf(source: string): string {
  const start = source.indexOf("<template>");
  const end = source.lastIndexOf("</template>");
  return start >= 0 && end > start ? source.slice(start, end) : "";
}

function offenders(pattern: RegExp, scope: "template" | "file" = "template"): string[] {
  return sources
    .filter(({ source }) => pattern.test(scope === "template" ? templateOf(source) : source))
    .map(({ file }) => file);
}

describe("Marketing canônico em Nuxt UI", () => {
  it("não tem controle HTML cru", () => {
    expect(offenders(/<(?:button|input|select|textarea|form|table)\b/i)).toEqual([]);
  });

  it("não usa o kit antigo, fora os cinco campos de data e hora", () => {
    expect(
      offenders(/<Ui(?!(?:DateField|DateRangeField|TimeField|TimeRangeField|DateTimeField)\b)[A-Z]/),
    ).toEqual([]);
  });

  it("não escreve :ui por instância", () => {
    expect(offenders(/\s:ui=|\sui="/)).toEqual([]);
  });

  it("não usa tamanho de texto arbitrário", () => {
    expect(offenders(/\btext-\[\d+(?:\.\d+)?(?:px|rem|em)\]/, "file")).toEqual([]);
  });

  it("não monta barra de base à mão", () => {
    expect(
      offenders(/class="[^"]*\b(?:fixed|sticky)\b[^"]*\bbottom-/),
    ).toEqual([]);
  });

  it("não decide a árvore por régua de largura em JS", () => {
    expect(offenders(/useMediaQuery\(\s*["'`]\((?:max|min)-width/, "file")).toEqual([]);
  });

  it("o ⋯ é o do kit: nenhum menu de reticências montado à mão", () => {
    expect(offenders(/ellipsis/)).toEqual([]);
  });
});
