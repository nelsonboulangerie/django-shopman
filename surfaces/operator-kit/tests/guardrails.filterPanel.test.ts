import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Trava do painel de filtros único (WP-FASE2-UX-OPERADOR, K4).
//
// 1. Nos apps migrados, recorte de lista é o `OperatorFilterPanel`: o `FilterBar`
//    ("+ Filtro" com um popover por campo) saiu do Gestor em 09/10/2026.
// 2. Toda tela que guarda favorito existe no registro do servidor
//    (`shopman/backstage/api/saved_views.py`, `SCREENS`): uma tela nova que esquecesse
//    de se registrar mostraria "Salvar como favorito" e receberia 400 ao salvar. Vale
//    também para a faixa de filtros rápidos (`OperatorQuickFilters`), que lê os
//    favoritos fixados da mesma tela.
// 3. O recorte de todo dia é UM toque, com contagem (dono, P1 de 02/10/2026): filtro
//    rápido declarado no painel (`:quick`) só existe ao lado da faixa
//    (`OperatorQuickFilters`) na mesma tela. Escondido só no painel são dois toques e
//    nenhuma contagem: foi a regressão das Encomendas do PDV (#1610).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const repoDir = resolve(surfacesDir, "..");
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);
const MIGRATED = ["orders-nuxt"];

function vueAndTs(dir: string, found: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return found;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) vueAndTs(full, found);
    else if (full.endsWith(".vue") || full.endsWith(".ts")) found.push(full);
  }
  return found;
}

const registry = new Set(
  [
    ...readFileSync(join(repoDir, "shopman/backstage/api/saved_views.py"), "utf8").matchAll(
      /\("([a-z]+)", "([a-z_]+)"\): Screen\(/g,
    ),
  ].map(([, surface, screen]) => `${surface}/${screen}`),
);

describe("painel de filtros único", () => {
  it("o registro do servidor foi lido", () => {
    expect(registry.size).toBeGreaterThanOrEqual(5);
  });

  it("nos apps migrados, nenhum FilterBar", () => {
    const offenders = MIGRATED.flatMap((app) =>
      vueAndTs(join(surfacesDir, app, "app"))
        .filter((file) => /<FilterBar\b/.test(readFileSync(file, "utf8")))
        .map((file) => relative(surfacesDir, file)),
    );
    expect(offenders).toEqual([]);
  });

  it("toda tela que guarda favorito está no registro do servidor", () => {
    const used = new Set<string>();
    for (const app of [...OPERATOR_SURFACES, "operator-kit"]) {
      for (const file of vueAndTs(join(surfacesDir, app, "app"))) {
        const source = readFileSync(file, "utf8");
        for (const match of source.matchAll(/<(?:OperatorFilterPanel|OperatorQuickFilters)\b[\s\S]*?\/>/g)) {
          const surface = match[0].match(/\bsurface="([a-z]+)"/)?.[1];
          const screen = match[0].match(/\bscreen="([a-z_]+)"/)?.[1];
          if (surface && screen) used.add(`${surface}/${screen}`);
        }
        for (const match of source.matchAll(/useSavedViews(?:<[^>]*>)?\("([a-z]+)", "([a-z_]+)"\)/g)) {
          used.add(`${match[1]}/${match[2]}`);
        }
      }
    }
    expect(used.size).toBeGreaterThanOrEqual(5);
    expect([...used].filter((key) => !registry.has(key))).toEqual([]);
  });

  it("filtro rápido no painel só ao lado da faixa de filtros rápidos", () => {
    const offenders: string[] = [];
    for (const app of OPERATOR_SURFACES) {
      for (const file of vueAndTs(join(surfacesDir, app, "app"))) {
        if (!file.endsWith(".vue")) continue;
        const source = readFileSync(file, "utf8");
        const hidden = [...source.matchAll(/<OperatorFilterPanel\b[\s\S]*?\/>/g)].some((match) => /\s:quick=/.test(match[0]));
        if (hidden && !/<OperatorQuickFilters\b/.test(source)) offenders.push(relative(surfacesDir, file));
      }
    }
    expect(offenders).toEqual([]);
  });
});
