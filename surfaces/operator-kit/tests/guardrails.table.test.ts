import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Trava da tabela da suíte (WP-FASE2-UX-OPERADOR, K1).
//
// 1. Nos apps já migrados, lista é `OperatorTable`: compacta por padrão, Exibir, estado
//    da tela e a célula que quebra. Uma `NuxtTable` crua numa tela desses apps é uma
//    tabela que voltou a ser montada à mão (era assim nas cinco do Gestor até 09/10/2026).
// 2. Em lugar nenhum a tela escreve `:ui` na `OperatorTable`: a densidade é o único
//    `:ui` da tabela e mora na peça (regra do dono: sem `:ui` por instância).
//
// Os apps fora desta lista entram quando a onda de cada um trocar as tabelas pela peça.
// O B.I. entrou no acabamento da fase 2: as tabelas dele são de LEITURA, o corpo de um
// `OperatorReadingCard`, e por isso usam `in-card` (o cartão da tabela vira `soft`,
// nunca `outline` dentro de `outline`; trava abaixo).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);

/** Apps em que lista de trabalho é só `OperatorTable`. */
const MIGRATED = ["orders-nuxt", "marketing-nuxt", "bi-nuxt"];

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

describe("tabela da suíte: OperatorTable", () => {
  it("nos apps migrados, nenhuma NuxtTable crua", () => {
    const offenders = MIGRATED.flatMap((app) =>
      vueFiles(join(surfacesDir, app, "app"))
        .filter((file) => /<NuxtTable\b/.test(readFileSync(file, "utf8")))
        .map((file) => relative(surfacesDir, file)),
    );
    expect(offenders).toEqual([]);
  });

  it("nenhuma tela escreve :ui na OperatorTable", () => {
    const offenders: string[] = [];
    for (const app of [...OPERATOR_SURFACES, "operator-kit"]) {
      for (const file of vueFiles(join(surfacesDir, app, "app"))) {
        const source = readFileSync(file, "utf8");
        for (const match of source.matchAll(/<OperatorTable\b([^>]*)>/g)) {
          if (/(^|\s)(:ui|ui)=/.test(match[1] ?? "")) offenders.push(relative(surfacesDir, file));
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("no B.I., a tabela dentro do quadro de leitura diz in-card (cartão soft dentro do cartão)", () => {
    const offenders: string[] = [];
    for (const file of vueFiles(join(surfacesDir, "bi-nuxt", "app"))) {
      const source = readFileSync(file, "utf8");
      for (const match of source.matchAll(/<OperatorTable\b([^>]*)>/g)) {
        if (!/(^|\s)in-card(\s|=|$)/.test(match[1] ?? "")) offenders.push(relative(surfacesDir, file));
      }
    }
    expect(offenders).toEqual([]);
  });

  it("o Gestor usa a peça nas suas listas", () => {
    const uses = vueFiles(join(surfacesDir, "orders-nuxt", "app")).filter((file) =>
      /<OperatorTable\b/.test(readFileSync(file, "utf8")),
    );
    expect(uses.length).toBeGreaterThanOrEqual(5);
  });
});
