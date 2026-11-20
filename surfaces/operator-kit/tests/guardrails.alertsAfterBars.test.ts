import { existsSync, readdirSync, readFileSync } from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { OPERATOR_KIT_SURFACES } from "./support/surfaceRegistry";

// O aviso da tela vem depois de TODAS as barras do topo (dono, 20/11/2026, DEV-2026-063:
// "é pra ficar na área do conteúdo, como primeiro conteúdo").
//
// O `OperatorPageHeader` desenha as `alerts` por último, depois de todas as linhas dele
// (`tests/components/OperatorPageHeaderAlertOrder.test.ts`). O que ele não controla é a
// barra que a tela monta FORA dele: posta logo depois do `</OperatorPageHeader>`, ela fica
// embaixo do aviso. Foi o Gestor de pedidos a 375 px: as abas das colunas ("Novos · Em
// preparo · Prontos") numa `OperatorToolbar` depois do cabeçalho, e o "Ana espera a
// resposta da equipe" entre a linha do chão e as abas. A barra da tela mora no `#below`
// (ou antes do cabeçalho, junto da linha do chão do celular).
//
// A varredura olha o irmão seguinte de cada cabeçalho (o do kit e os que o embrulham,
// como o `ProductionHeader`) e, se ele for um invólucro (`div`, `section`, `main`), o
// primeiro filho dele: barra ali é barra embaixo do aviso.
//
// ⚠️ Lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");

function vueFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" || entry.name.startsWith(".") ? [] : vueFiles(path);
    return entry.name.endsWith(".vue") ? [path] : [];
  });
}

/** Barra de topo: as peças de barra do kit e do Nuxt UI, abas, e o que se marca como barra. */
const BAR_TAG = /^(?:OperatorToolbar|NuxtDashboardToolbar|UDashboardToolbar|NuxtTabs|UTabs|OperatorQuickFilters|OperatorSectionBar|OperatorAppBar|FilterBar|\w+Tabs|\w+Toolbar)$/;
const BAR_ATTR = /\brole="tablist"|\bdata-[\w-]*(?:-tabs|-toolbar|-zone-bar|-section-bar)\b/;
const WRAPPER_TAG = /^(?:div|section|main|template)$/;

/** O fim do elemento que começa em `start` (abre `<tag`), contando aberturas e fechamentos da mesma tag. */
function elementEnd(source: string, start: number): number {
  const tag = /^<([A-Za-z][\w-]*)/.exec(source.slice(start))?.[1];
  if (!tag) return start;
  const re = new RegExp(`<${tag}\\b(?:[^>"']|"[^"]*"|'[^']*')*?(/?)>|</${tag}\\s*>`, "g");
  re.lastIndex = start;
  let depth = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(source))) {
    if (match[0].startsWith("</")) depth -= 1;
    else if (match[1] !== "/") depth += 1;
    if (depth === 0) return re.lastIndex;
  }
  return source.length;
}

/** A abertura do próximo elemento a partir de `from`, pulando espaço e comentário; `null` se vier um fechamento. */
function nextOpening(source: string, from: number): { tag: string; open: string; start: number } | null {
  let i = from;
  for (;;) {
    while (i < source.length && /\s/.test(source[i]!)) i += 1;
    if (source.startsWith("<!--", i)) {
      const end = source.indexOf("-->", i);
      i = end < 0 ? source.length : end + 3;
      continue;
    }
    break;
  }
  if (source[i] !== "<" || source[i + 1] === "/") return null;
  const match = /^<([A-Za-z][\w-]*)\b(?:[^>"']|"[^"]*"|'[^']*')*>/.exec(source.slice(i));
  if (!match) return null;
  return { tag: match[1]!, open: match[0], start: i };
}

function isBar(tag: string, open: string): boolean {
  return BAR_TAG.test(tag) || BAR_ATTR.test(open);
}

/** O template de um SFC (do primeiro `<template` ao último `</template>`). */
function templateOf(source: string): string {
  const start = source.indexOf("<template");
  const end = source.lastIndexOf("</template>");
  return start < 0 ? "" : source.slice(start, end < 0 ? undefined : end + "</template>".length);
}

/**
 * As barras que um template põe logo depois de um cabeçalho (`headers`: o do kit e os que
 * o embrulham). Devolve uma linha por barra: o cabeçalho e a tag da barra.
 */
export function barsAfterHeader(source: string, headers: readonly string[]): string[] {
  const template = templateOf(source);
  const found: string[] = [];
  for (const header of headers) {
    const open = new RegExp(`<${header}\\b`, "g");
    let match: RegExpExecArray | null;
    while ((match = open.exec(template))) {
      const end = elementEnd(template, match.index);
      let next = nextOpening(template, end);
      // Um invólucro (ou um `<template v-if>`) entra um nível: o primeiro filho dele.
      for (let depth = 0; next && depth < 2 && !isBar(next.tag, next.open) && WRAPPER_TAG.test(next.tag); depth += 1) {
        next = nextOpening(template, next.start + next.open.length);
      }
      if (next && isBar(next.tag, next.open)) found.push(`${header} → ${next.tag}`);
    }
  }
  return found;
}

/** Os cabeçalhos de um app: o do kit e os componentes dele que o embrulham (`*Header.vue`). */
function headersOf(files: readonly string[]): string[] {
  const wrappers = files
    .filter((path) => /\/components\//.test(path) && /Header\.vue$/.test(path))
    .filter((path) => /<OperatorPageHeader\b/.test(readFileSync(path, "utf8")))
    .map((path) => basename(path, ".vue"));
  return ["OperatorPageHeader", ...wrappers];
}

describe("guardrail: o aviso vem depois de todas as barras do topo", () => {
  it("o detector pega a barra depois do cabeçalho e deixa passar a do #below e a de antes", () => {
    // O Gestor antes do conserto (20/11/2026): as colunas em abas depois do cabeçalho.
    const gestorAntes = `<template><main data-compact-page>
      <OperatorCompactBar title="Pedidos" />
      <OperatorPageHeader title="Pedidos" :alerts="screenAlerts">
        <template #actions><NuxtTabs :items="viewTabs" /></template>
      </OperatorPageHeader>

      <!-- celular: as colunas viram abas -->
      <OperatorToolbar v-if="boardAsTabs" data-board-zone-bar>
        <NuxtTabs :items="phoneTabItems" />
      </OperatorToolbar>
      <section class="flex-1">conteúdo</section>
    </main></template>`;
    const gestorDepois = `<template><main data-compact-page>
      <OperatorCompactBar title="Pedidos" />
      <OperatorPageHeader title="Pedidos" :alerts="screenAlerts">
        <template #below>
          <OperatorToolbar v-if="boardAsTabs" data-board-zone-bar><NuxtTabs :items="phoneTabItems" /></OperatorToolbar>
        </template>
      </OperatorPageHeader>
      <section class="flex-1"><VolumeCheckBar /></section>
    </main></template>`;
    // A barra do celular que a linha do chão leva junto (antes do cabeçalho) não é defeito.
    const antesDoCabecalho = `<template><main>
      <div class="md:hidden" data-compact-settings-tabs><PosSettingsTabs /></div>
      <OperatorPageHeader title="Ajustes" :alerts="alerts" />
      <div class="min-h-0 flex-1"><slot /></div>
    </main></template>`;
    // Abas como primeiro filho do invólucro do conteúdo também ficam embaixo do aviso.
    const abasNoConteudo = `<template>
      <ProductionHeader title="Plano" :alerts="alerts" />
      <section class="flex-1"><template v-if="ready"><NuxtTabs :items="tabs" /></template></section>
    </template>`;
    const marcada = `<template><OperatorPageHeader title="X" /><div role="tablist"><button /></div></template>`;

    expect(barsAfterHeader(gestorAntes, ["OperatorPageHeader"])).toEqual(["OperatorPageHeader → OperatorToolbar"]);
    expect(barsAfterHeader(gestorDepois, ["OperatorPageHeader"])).toEqual([]);
    expect(barsAfterHeader(antesDoCabecalho, ["OperatorPageHeader"])).toEqual([]);
    expect(barsAfterHeader(abasNoConteudo, ["OperatorPageHeader", "ProductionHeader"])).toEqual([
      "ProductionHeader → NuxtTabs",
    ]);
    expect(barsAfterHeader(marcada, ["OperatorPageHeader"])).toEqual(["OperatorPageHeader → div"]);
  });

  it("a varredura acha os cabeçalhos dos apps (não passa por estar cega)", () => {
    let headers = 0;
    const wrappers = new Set<string>();
    for (const app of OPERATOR_KIT_SURFACES) {
      const files = vueFiles(join(surfacesDir, app, "app"));
      for (const name of headersOf(files)) if (name !== "OperatorPageHeader") wrappers.add(name);
      headers += files.filter((path) => /<OperatorPageHeader\b/.test(readFileSync(path, "utf8"))).length;
    }
    expect(headers).toBeGreaterThan(40);
    // O cabeçalho da Produção embrulha o do kit: a varredura olha depois dele também.
    expect([...wrappers]).toContain("ProductionHeader");
  });

  it("nenhum app de operador monta barra logo depois do cabeçalho (mora no #below)", () => {
    const offenders: string[] = [];
    for (const app of OPERATOR_KIT_SURFACES) {
      const files = vueFiles(join(surfacesDir, app, "app"));
      const headers = headersOf(files);
      for (const path of files) {
        for (const hit of barsAfterHeader(readFileSync(path, "utf8"), headers)) {
          offenders.push(`${relative(surfacesDir, path)}: ${hit}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
