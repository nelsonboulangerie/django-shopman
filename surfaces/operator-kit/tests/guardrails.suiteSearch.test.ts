import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { isSuiteScreenLabel } from "../app/presentation/suiteSearch";
import { DEPLOYED_OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Busca da suíte: trava de forma (V6-BUSCA; T-10, T-11, H01, H03 das auditorias v4).
//
// O que voltava sem isto:
//   - app sem busca nenhuma (a Central e o Marketing não tinham campo; a v4 tem);
//   - a tela que filtra a própria lista com um `UiSearchInput` cru no cabeçalho: no
//     celular a lupa só revelava aquele campo, e a suíte ficava fora de alcance;
//   - um segundo campo de busca na mesma linha ("dois campos confundem", retorno do dono
//     que motivou a busca única da v3).
//
// ⚠️ Lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");

function vueFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory())
      return entry.name === "node_modules" || entry.name.startsWith(".")
        ? []
        : vueFiles(path);
    return entry.name.endsWith(".vue") ? [path] : [];
  });
}

function appSources(app: string): Array<{ path: string; source: string }> {
  return vueFiles(join(surfacesDir, app, "app")).map((path) => ({
    path,
    source: readFileSync(path, "utf8"),
  }));
}

/** O conteúdo de cada `<template #search>` (ou `v-slot:search`) de um SFC. */
function searchSlots(source: string): string[] {
  const slots: string[] = [];
  const open = /<template\b[^>]*(?:#search|v-slot:search)\b[^>]*>/g;
  let match: RegExpExecArray | null;
  while ((match = open.exec(source))) {
    const start = match.index + match[0].length;
    const end = source.indexOf("</template>", start);
    slots.push(source.slice(start, end === -1 ? undefined : end));
  }
  return slots;
}

describe("busca da suíte (V6-BUSCA)", () => {
  it("os oito apps e a Central têm a busca da suíte no lugar da v4", () => {
    const missing = DEPLOYED_OPERATOR_SURFACES.filter((app) => {
      const sources = appSources(app);
      // O cabeçalho do kit já traz a busca (padrão `search = true`); quem não o usa
      // monta a peça direto (a Central, a Venda do PDV).
      return !sources.some(({ source }) =>
        /<OperatorPageHeader\b|<OperatorSuiteSearch\b/.test(source),
      );
    });
    expect(missing).toEqual([]);
  });

  it("a Central tem a busca da suíte na barra do topo do shell, como os outros apps (fase 2)", () => {
    const hub = appSources("hub-nuxt")
      .map(({ source }) => source)
      .join("\n");
    // A barra grande (`hero`) da v4 saiu com a fase 2: a Central veste o shell e a busca
    // é a do `OperatorPageHeader`, campo na mesa e lupa no celular.
    expect(hub).toMatch(/<OperatorPageHeader\b[^>]*search-placeholder=/s);
    expect(hub).not.toMatch(/variant="hero"/);
  });

  it("o cabeçalho nasce com a busca da suíte (só se desliga por escrito)", () => {
    const header = readFileSync(
      join(kitDir, "app/components/OperatorPageHeader.vue"),
      "utf8",
    );
    expect(header).toMatch(/search: true/);
    expect(header).toMatch(/<slot name="search"\s*>\s*<OperatorSuiteSearch\b/);
    const off = DEPLOYED_OPERATOR_SURFACES.flatMap((app) =>
      appSources(app)
        .filter(({ source }) =>
          /<OperatorPageHeader\b[^>]*:search="false"/.test(source),
        )
        .map(({ path }) => relative(surfacesDir, path)),
    );
    expect(off).toEqual([]);
  });

  it("o `#search` do cabeçalho é sempre a busca da suíte, e uma só", () => {
    const offenders: string[] = [];
    for (const app of DEPLOYED_OPERATOR_SURFACES) {
      for (const { path, source } of appSources(app)) {
        for (const slot of searchSlots(source)) {
          // Cabeçalho do app que só repassa o slot (o `MarketingPageHeader`): quem
          // preenche é a tela, e a tela passa por esta mesma varredura.
          if (/^\s*<slot name="search"\s*\/>\s*$/.test(slot)) continue;
          const suite = slot.match(/<OperatorSuiteSearch\b/g)?.length ?? 0;
          const raw = /<UiSearchInput\b|<input\b[^>]*type="search"/.test(slot);
          if (suite !== 1 || raw) offenders.push(relative(surfacesDir, path));
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("a busca é o canônico: NuxtDashboardSearch com os níveis como grupos (fase 2, K6)", () => {
    const source = readFileSync(join(kitDir, "app/components/OperatorSuiteSearch.vue"), "utf8");
    const template = source.slice(source.indexOf("<template>"));
    expect(template).toMatch(/<NuxtDashboardSearchButton\b/);
    expect(template).toMatch(/<NuxtDashboardSearch\b[^>]*preserve-group-order/s);
    // Sem Modal, Tabs ou CommandPalette montados à mão em volta: o painel é o oficial.
    expect(template).not.toMatch(/<Nuxt(?:Modal|Tabs|CommandPalette)\b/);
    // O atalho próprio do DashboardSearch fica desligado: as teclas são do kit.
    expect(template).toMatch(/shortcut=""/);
  });
  it("o rótulo da tela diz o artigo: \"filtrando <o|a|os|as> <nome>\" (vira do/da/dos/das)", () => {
    // "Tirar o filtro “x” de as campanhas" saía porque a frase colava "de" no rótulo. A
    // contração vem do artigo que a tela escreve; rótulo sem artigo não tem como contrair.
    const offenders: string[] = [];
    const apps = [...DEPLOYED_OPERATOR_SURFACES, "operator-kit"];
    for (const app of apps) {
      const files = app === "operator-kit" ? vueFiles(join(kitDir, "app")) : vueFiles(join(surfacesDir, app, "app"));
      for (const path of files) {
        const source = readFileSync(path, "utf8");
        // `screen-label` vai direto ao OperatorSuiteSearch; no Produção, `search-label`
        // do ProductionHeader é repassado como `screen-label`.
        const literal = path.endsWith("RecipeHeader.vue") || /recipes\/index\.vue$/.test(path)
          ? /\sscreen-label="([^"]*)"/g
          : /\s(?:screen|search)-label="([^"]*)"/g;
        for (const match of source.matchAll(literal)) {
          if (!isSuiteScreenLabel(match[1]!)) offenders.push(`${relative(surfacesDir, path)}: ${match[1]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
