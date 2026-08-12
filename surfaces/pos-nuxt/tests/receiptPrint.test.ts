// Contrato de impressão do recibo (spec §D3 — rolo térmico, default 80mm).
//
// Isto não testa formatação (isso é `presentation/receipt`, coberto em
// presentation.test.ts) — testa a GEOMETRIA, que mora em CSS e some num refactor
// sem ninguém perceber até sair papel torto no balcão. Os invariantes:
//
//   1. a largura impressa é declarada por nós, não pelo driver da impressora;
//   2. a largura tem um dono só (as vars do rolo) e o `@page` não diverge delas;
//   3. a largura é configurável em runtime pela var, com o literal como rede;
//   4. toda `var()` no `@page` carrega fallback — uma que não resolve derruba o
//      `size` inteiro e a página volta ao driver, calada;
//   5. o recibo é irmão do app no `body`, para o print CSS poder escondê-lo com
//      `display: none` (senão volta a sair página em branco).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

// Os comentários do print CSS citam as regras erradas que este teste proíbe
// (`size: … auto`, `visibility: hidden`) para explicar por que elas caíram —
// as asserções olham só o CSS que o navegador aplica.
const css = read("../app/assets/css/tailwind.css").replace(/\/\*[\s\S]*?\*\//g, "");
const receiptVue = read("../app/components/PosReceipt.vue");
const indexVue = read("../app/pages/index.vue");

/** Valor de uma custom property declarada no `:root` do tema. */
function cssVar(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*([^;]+);`));
  expect(match, `--${name} deve existir em tailwind.css`).not.toBeNull();
  return match![1]!.trim();
}

const pageRule = (() => {
  const match = css.match(/@page\s*\{([^}]*)\}/);
  expect(match, "tailwind.css deve declarar um bloco @page para o recibo").not.toBeNull();
  return match![1]!;
})();

/** Todas as declarações de um descritor no `@page`, na ordem em que aparecem. */
const pageDescriptors = (name: string): string[] => {
  const found = [...pageRule.matchAll(new RegExp(`\\b${name}:\\s*([^;]+);`, "g"))]
    .map((match) => match[1]!.trim());
  expect(found.length, `@page deve declarar \`${name}\``).toBeGreaterThan(0);
  return found;
};

describe("geometria do rolo", () => {
  it("declara tamanho e margem em vez de deixar o driver decidir", () => {
    // Duas declarações de propósito: o literal é a rede para uma engine que não
    // aceite `var()` em `@page` (descarta a linha seguinte no parse e fica com
    // esta); a versão com var é o ponto de configuração. Ordem importa.
    const [sizeLiteral, sizeConfigurable, ...sizeExtra] = pageDescriptors("size");
    expect(sizeLiteral).toBe(`${cssVar("pos-roll-width")} ${cssVar("pos-roll-height")}`);
    expect(sizeConfigurable).toBe(
      `var(--pos-roll-width, ${cssVar("pos-roll-width")}) `
      + `var(--pos-roll-height, ${cssVar("pos-roll-height")})`,
    );
    expect(sizeExtra, "só literal + configurável").toEqual([]);

    const [marginLiteral, marginConfigurable, ...marginExtra] = pageDescriptors("margin");
    expect(marginLiteral).toBe(`${cssVar("pos-roll-margin-y")} ${cssVar("pos-roll-margin-x")}`);
    expect(marginConfigurable).toBe(
      `var(--pos-roll-margin-y, ${cssVar("pos-roll-margin-y")}) `
      + `var(--pos-roll-margin-x, ${cssVar("pos-roll-margin-x")})`,
    );
    expect(marginExtra, "só literal + configurável").toEqual([]);
  });

  it("não usa `auto` no descritor `size`", () => {
    // `size: 80mm auto` é inválido (não se mistura <length> com auto): o
    // navegador descarta a regra inteira e a página volta ao padrão do driver
    // (verificado no Chrome — saía Letter). Um `auto` aqui reabre o bug original.
    expect(pageRule).not.toMatch(/\bauto\b/);
  });

  it("dá fallback a toda `var()` do @page", () => {
    // Medido no Chrome: `size: 80mm 297mm; size: var(--x)` com `--x` ausente NÃO
    // cai para o literal anterior — derruba o `size` inteiro e a página volta ao
    // Letter, sem aviso. O fallback inline é o que impede esse buraco.
    const substitutions = [...pageRule.matchAll(/var\(([^)]*)\)/g)].map((match) => match[1]!);
    expect(substitutions.length, "o @page deve ser configurável por var").toBeGreaterThan(0);
    for (const substitution of substitutions) {
      expect(substitution, `var(${substitution}) precisa de fallback`).toMatch(/,\s*\S/);
    }
  });

  it("deriva a largura útil do rolo menos as duas margens", () => {
    expect(cssVar("pos-receipt-width")).toBe(
      "calc(var(--pos-roll-width) - 2 * var(--pos-roll-margin-x))",
    );
  });

  it("não pede mais largura do que o cabeçote alcança", () => {
    // Uma térmica não imprime até a borda do papel: ~4mm de cada lado ficam fora
    // do alcance do cabeçote (80mm de rolo → 72mm impressos). Layout mais largo
    // que isso não ganha espaço, só empurra a coluna da direita para fora.
    const mm = (value: string) => {
      expect(value, "a geometria do rolo é em mm").toMatch(/^[\d.]+mm$/);
      return Number.parseFloat(value);
    };
    const roll = mm(cssVar("pos-roll-width"));
    const usable = roll - 2 * mm(cssVar("pos-roll-margin-x"));
    expect(usable).toBeGreaterThan(0);
    expect(usable).toBeLessThanOrEqual(roll - 8);
  });
});

describe("o recibo obedece à largura do rolo", () => {
  it("trava a largura de `.pos-receipt` na largura útil", () => {
    const rule = css.match(/\.pos-receipt\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/max-width:\s*var\(--pos-receipt-width\)/);
    expect(rule).toMatch(/width:\s*100%/);
  });

  it("não fixa largura própria no componente", () => {
    // A largura tem um dono: `.pos-receipt`. Um `w-[80mm]` no template volta a
    // duplicar o número do rolo em dois lugares.
    const root = receiptVue.match(/<template>\s*<div class="([^"]+)"/)?.[1];
    expect(root, "a raiz do PosReceipt deve ter classe").toBeTruthy();
    expect(root).toContain("pos-receipt");
    expect(root).not.toMatch(/\b(max-)?w-\[/);
    expect(root).not.toMatch(/\b(max-)?w-(?:full|screen|\d)/);
  });
});

describe("a área de impressão é irmã do app", () => {
  it("teleporta o #pos-print-area para o body", () => {
    expect(indexVue).toMatch(/<Teleport to="body">\s*<div v-if="result" id="pos-print-area">/);
  });

  it("esconde o app com display none, não com visibility", () => {
    const print = css.match(/@media print\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
    expect(print).toMatch(/body\s*>\s*\*:not\(#pos-print-area\)\s*\{\s*display:\s*none/);
    // `visibility: hidden` mantém os boxes ocupando espaço: o recibo saía com
    // páginas em branco atrás e não paginava junto com o próprio conteúdo.
    expect(print).not.toMatch(/visibility:\s*hidden/);
  });
});
