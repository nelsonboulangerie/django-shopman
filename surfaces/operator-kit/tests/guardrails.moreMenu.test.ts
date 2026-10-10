import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Trava do ⋯ ÚNICO (WP-FASE2-UX-OPERADOR, D9): "Mais ações" se escreve com o
// `OperatorMoreMenu`, nunca com um botão de reticências montado na tela.
//
// Motivo medido (09/10/2026): o Gestor tinha três formas de ⋯ (`outline` na fila e no
// catálogo, `ellipsis-vertical` na linha da tabela, botão rotulado no pedido), o
// Marketing quatro, e o ⋯ sumia no celular em telas inteiras. O ícone de reticências
// fora da peça é o sinal de um ⋯ feito à mão.
//
// Exceção só com motivo, e o número só cai. Os apps ainda fora do shell (Marketing,
// Compras, Produção, PDV) desenham o ⋯ com `UiPopover` e outro ícone: entram na trava
// quando a onda de cada um trocar o menu pela peça.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const ROOTS = [...OPERATOR_SURFACES, "operator-kit"].map((dir) => join(surfacesDir, dir, "app"));
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);

const ELLIPSIS = /i-lucide-ellipsis(?:-vertical)?\b/g;

/** Onde o ícone de reticências é legítimo, com o motivo e o teto. */
const ALLOWED: Record<string, { max: number; reason: string }> = {
  "operator-kit/app/components/OperatorMoreMenu.vue": {
    max: 1,
    reason: "a peça",
  },
  "operator-kit/app/components/OperatorPhoneMenu.vue": {
    max: 1,
    reason: "navegação: o menu do operador na barra do topo, não ações da tela",
  },
  "operator-kit/app/components/OperatorSectionBar.vue": {
    max: 1,
    reason: "navegação: o \"Mais\" da barra do polegar dos apps fora do shell",
  },
  "orders-nuxt/app/pages/[ref].vue": {
    max: 2,
    reason: "abre um PAINEL (o pedido inteiro), não uma lista: celular e mesa",
  },
  "bi-nuxt/app/pages/explore.vue": {
    max: 1,
    reason: "abre um painel com campo de texto (o nome do cenário a salvar)",
  },
};

function vueFiles(dir: string, found: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return found;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) vueFiles(full, found);
    else if (full.endsWith(".vue")) found.push(full);
  }
  return found;
}

function ellipsisCounts(): Map<string, number> {
  const counts = new Map<string, number>();
  for (const root of ROOTS) {
    for (const file of vueFiles(root)) {
      const hits = readFileSync(file, "utf8").match(ELLIPSIS)?.length ?? 0;
      if (hits) counts.set(relative(surfacesDir, file), hits);
    }
  }
  return counts;
}

describe("⋯ único: Mais ações só pelo OperatorMoreMenu", () => {
  it("nenhum botão de reticências fora da peça e das exceções declaradas", () => {
    const offenders = [...ellipsisCounts()]
      .filter(([file, hits]) => hits > (ALLOWED[file]?.max ?? 0))
      .map(([file, hits]) => `${file}: ${hits}`);
    expect(offenders, "use <OperatorMoreMenu :items label> (README, \"Mais ações\")").toEqual([]);
  });

  it("o teto das exceções acompanha o código (o número só cai)", () => {
    const counts = ellipsisCounts();
    const stale = Object.entries(ALLOWED)
      .filter(([file, { max }]) => (counts.get(file) ?? 0) < max)
      .map(([file, { max }]) => `${file}: teto ${max}, hoje ${counts.get(file) ?? 0}`);
    expect(stale, "baixe o teto em ALLOWED").toEqual([]);
  });

  it("o ⋯ vertical não existe na suíte", () => {
    const vertical = [...ROOTS.flatMap((root) => vueFiles(root))]
      .filter((file) => readFileSync(file, "utf8").includes("i-lucide-ellipsis-vertical"))
      .map((file) => relative(surfacesDir, file));
    expect(vertical).toEqual([]);
  });
});
