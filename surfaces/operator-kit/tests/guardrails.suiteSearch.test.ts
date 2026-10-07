import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

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

  it("a Central tem a barra grande da busca no cabeçalho (v4 `hub.jpg`, v3 `depois-hub-celular`)", () => {
    const hub = appSources("hub-nuxt")
      .map(({ source }) => source)
      .join("\n");
    expect(hub).toMatch(/<OperatorSuiteSearch\b[^>]*variant="hero"/);
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
});
