import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Trava da barra de seleção (WP-FASE2-UX-OPERADOR, K2): UMA por tela, a `OperatorBulkBar`.
//
// Até 09/10/2026 o Gestor tinha duas barras de lote feitas à mão: a da Fila numa
// toolbar extra no topo e a do Catálogo numa toolbar de rodapé, com os pares de gestos
// opostos em pesos diferentes (Pausar/Ativar contornados, Ocultar/Exibir discretos).
// Agora a seleção mora no `#selection` do cabeçalho (mesa) e na base (celular).
//
// Os apps fora desta lista entram quando a onda de cada um trocar a barra pela peça.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);
const MIGRATED = ["orders-nuxt"];

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

const files = MIGRATED.flatMap((app) =>
  vueFiles(join(surfacesDir, app, "app")).map((file) => ({
    file: relative(surfacesDir, file),
    source: readFileSync(file, "utf8"),
  })),
);

describe("barra de seleção: só a OperatorBulkBar", () => {
  it("nenhuma barra de lote à mão (toolbar de rodapé ou faixa de seleção)", () => {
    const offenders = files
      .filter(({ source }) => /<OperatorToolbar\b[^>]*\bas="footer"/.test(source) || /data-bulk-done/.test(source))
      .map(({ file }) => file);
    expect(offenders).toEqual([]);
  });

  it("toda tela com seleção a põe nos dois lugares: o cabeçalho e a base", () => {
    const screens = files.filter(({ source }) => /#selection\b/.test(source));
    expect(screens.map(({ file }) => file).sort()).toEqual([
      "orders-nuxt/app/pages/catalog.vue",
      "orders-nuxt/app/pages/index.vue",
    ]);
    for (const { file, source } of screens) {
      const bars = source.match(/<OperatorBulkBar\b/g)?.length ?? 0;
      const base = source.match(/<OperatorBulkBar\b[^>]*?placement="base"/gs)?.length ?? 0;
      expect({ file, bars, base }).toEqual({ file, bars: 2, base: 1 });
    }
  });
});
