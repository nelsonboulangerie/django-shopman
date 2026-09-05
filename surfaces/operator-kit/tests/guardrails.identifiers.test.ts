import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrail de CONVENÇÃO: identificador é em inglês (CLAUDE.md), com três
// exceções que são regra e não julgamento — `cpf`/`cnpj`/`cep`, **prosa**
// (comentário, docstring, cópia de tela) e campo de API de terceiro.
//
// ## Por que isto existe, e por que é um catraca e não um teste comum
//
// A limpeza está planejada (docs/plans/WP-IDENT-PT-BR.md) e NÃO roda agora:
// rename em massa é hostil a merge, e o gatilho é a fila de merge vazia. Só que
// o risco de uma limpeza adiada não é ela atrasar — é ela **crescer calada**
// enquanto espera, porque ninguém está olhando o número.
//
// Então a dívida vira NOMEADA e só pode encolher — o mesmo idioma que a casa já
// usa para as mutações de caixa no inventário de fallbacks. Passar do baseline
// reprova; ficar abaixo dele também reprova, pedindo que o número desça junto.
// Assim o WP não depende de alguém lembrar: o repositório cobra.
//
// ## Medir identificador é diferente de dar grep
//
// ⚠️ `grep -c '\bresposta\b'` devolve 94 ocorrências em 58 arquivos — e quase
// tudo é comentário e string, que a regra manda deixar em português. A primeira
// medição desta frente errou por um fator de ~10 exatamente assim. Aqui os
// comentários e literais são removidos ANTES, e só declarações contam.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Dívida medida em 02/09/2026. Só desce. Ver WP-IDENT-PT-BR.md. */
const BASELINE = 35;

// Allowlist do que já se sabe existir — NÃO é detector. Nome novo em pt-br não
// aparece aqui; contra isso vale a revisão e a varredura morfológica periódica
// (-cao, -mento, -avel, -eiro) descrita no WP. Cognatos (`total`, `data`,
// `fiscal`) e a exceção documentada do caixa (`sangria`/`suprimento`) ficam de
// fora de propósito.
const PT_IDENTIFIERS = new Set([
  "resposta", "resultado", "linhas", "corpo", "assinatura", "movimento", "opcoes",
  "secao", "chamada", "chaveDoGesto", "novaChave", "comChave", "ultimaTentativa",
  "abrirTela", "cancelarComAprovacao", "ehRotaDeAutenticacao", "prefereMenosMovimento",
  "aprovacao", "denominacoes", "tentativa", "primeira", "terceira", "duracao",
  "capacidade", "comCliente", "semCliente", "comInsumo", "semInsumo", "semNome",
  "semQuantidade",
]);

const DECL = /\b(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)/g;

function stripNoise(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''")
    .replace(/`(?:[^`\\]|\\.)*`/g, "``");
}

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".nuxt" || entry === ".output") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (full.endsWith(".ts") || full.endsWith(".vue")) found.push(full);
  }
  return found;
}

function ptDeclarations(): { total: number; where: string[] } {
  const where: string[] = [];
  for (const file of sourceFiles(surfacesDir)) {
    const clean = stripNoise(readFileSync(file, "utf8"));
    for (const match of clean.matchAll(DECL)) {
      const name = match[1]!;
      if (PT_IDENTIFIERS.has(name)) {
        where.push(`${file.slice(surfacesDir.length + 1)} → ${name}`);
      }
    }
  }
  return { total: where.length, where };
}

describe("convenção: identificador em inglês — dívida nomeada, e ela só encolhe", () => {
  it(`não cresce além do baseline de ${BASELINE} declarações`, () => {
    const { total, where } = ptDeclarations();
    expect(
      total,
      `A dívida de identificador em pt-br CRESCEU: ${total} declarações (baseline ${BASELINE}).\n` +
        `Identificador é em inglês; comentário e cópia de tela continuam em português.\n` +
        `Onde:\n  ${where.join("\n  ")}`,
    ).toBeLessThanOrEqual(BASELINE);
  });

  it(`o baseline acompanha a limpeza — se caiu, desça o número`, () => {
    const { total } = ptDeclarations();
    expect(
      total,
      `A dívida caiu para ${total}. Baixe BASELINE para ${total} neste arquivo — ` +
        `catraca que não aperta deixa a dívida voltar sem ninguém ver.`,
    ).toBeGreaterThanOrEqual(BASELINE);
  });
});
