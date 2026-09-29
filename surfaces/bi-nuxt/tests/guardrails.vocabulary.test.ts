import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Sigla não vira tela (decisão do dono, 22/09/2026: "jargão a traduzir, com toda
// certeza!"). `RevPASH` virou "Receita por assento por hora" e `RFM` virou
// "Segmentos de cliente" / "recência, frequência e valor".
//
// A trava lê o TEXTO — template de `.vue` e código de `.ts` — e deixa passar
// comentário e docstring de propósito: lá a sigla é o atalho de quem mantém o
// código até a literatura, e não chega ao operador.
const APP = fileURLToPath(new URL("../app", import.meta.url));

// Exceção declarada: `app/generated/` é o contrato gerado a partir dos dataclasses
// do Python (`BIRevpashRow`, `revpash_q`). São identificadores de campo, que por
// regra da casa seguem em inglês — e nada ali rende em tela.
const EXCLUDED_DIRS = new Set(["generated"]);

const FORBIDDEN = [
  { term: "RevPASH", pattern: /RevPASH/, say: "Receita por assento por hora" },
  { term: "RFM", pattern: /\bRFM\b/, say: "recência, frequência e valor" },
];

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return EXCLUDED_DIRS.has(entry.name) ? [] : walk(full);
    return /\.(vue|ts)$/.test(entry.name) ? [full] : [];
  });
}

// Tira bloco de comentário e linha inteira de comentário (`//`, `*`, `<!-- -->`).
//
// De propósito NÃO mexe em comentário no fim de linha de código: comer `//` solto
// comeria também `https://`, e uma trava que apaga código é uma trava que deixa
// passar. O que sobra é o texto que o operador pode ler.
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return !trimmed.startsWith("//") && !trimmed.startsWith("*");
    })
    .join("\n");
}

const FILES = walk(APP);

describe("vocabulário do B.I.: a sigla não volta para a tela", () => {
  it("a varredura enxerga a superfície inteira", () => {
    // Guarda da guarda: glob quebrado passa vazio e verde. As duas telas que a
    // decisão do dono tocou têm que estar entre os arquivos lidos.
    expect(FILES.length).toBeGreaterThan(20);
    const seen = FILES.map((file) => relative(APP, file));
    expect(seen).toContain("pages/profiles.vue");
    expect(seen).toContain("pages/customers.vue");
  });

  it("o detector tem dente", () => {
    // Positivo de controle: sem isto, um `stripComments` guloso demais faria a
    // suíte inteira passar por apagar o que deveria ler.
    const amostra = stripComments("<h2>RevPASH por faixa</h2>\n// Segmentos RFM no CRM\n");
    expect(FORBIDDEN[0]!.pattern.test(amostra)).toBe(true);
    expect(FORBIDDEN[1]!.pattern.test(amostra)).toBe(false);
  });

  it.each(FORBIDDEN)("nenhum texto de tela diz $term", ({ pattern, say }) => {
    const offenders = FILES.filter((file) =>
      pattern.test(stripComments(readFileSync(file, "utf8"))),
    ).map((file) => relative(APP, file));

    expect(offenders, `escreva "${say}" no lugar da sigla`).toEqual([]);
  });
});
