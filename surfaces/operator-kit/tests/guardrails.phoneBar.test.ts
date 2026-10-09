import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Barra de cima do celular (56px): trava do Atualizar solto (T-06 da auditoria v4).
//
// A barra leva selo, título, ponto ao vivo, lupa, sino (Avisos) e o ⋯. Nada além disso
// (SPEC4 item 7). O que voltava sem isto: o Compras punha um botão "Atualizar" avulso
// na barra do Painel e do Comprar, e o Marketing outro no Enviados, enquanto a Base do
// Compras e as outras telas do Marketing já o levavam para o ⋯ (com a tecla R onde há
// teclado). Atualizar dentro do ⋯ é permitido: os itens do menu moram no script e o
// componente do menu (`*Menu`) é retirado antes da varredura.
//
// Onde a barra é montada: o `#phone-actions` do `OperatorPageHeader` (e dos cabeçalhos
// que o repassam) e as barras próprias marcadas com `data-*-phone-actions` (a Central).
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

/** O elemento inteiro que começa em `start` (abre `<tag`), contando aberturas e fechamentos da mesma tag. */
function elementAt(source: string, start: number): string {
  const tag = /^<([A-Za-z][\w-]*)/.exec(source.slice(start))?.[1];
  if (!tag) return "";
  const firstEnd = source.indexOf(">", start);
  if (source[firstEnd - 1] === "/") return source.slice(start, firstEnd + 1);
  const re = new RegExp(`<${tag}\\b[^>]*?(/?)>|</${tag}\\s*>`, "g");
  re.lastIndex = start;
  let depth = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(source))) {
    if (match[0].startsWith("</")) depth -= 1;
    else if (match[1] !== "/") depth += 1;
    if (depth === 0) return source.slice(start, re.lastIndex);
  }
  return source.slice(start);
}

/** Cada trecho que vai para a barra de 56px do celular num SFC. */
export function phoneBarBlocks(source: string): string[] {
  const template = source.slice(source.indexOf("<template"));
  const blocks: string[] = [];
  const open = /<template\b[^>]*(?:#phone-actions|v-slot:phone-actions)\b[^>]*>|<[A-Za-z][\w-]*\b[^>]*\bdata-[\w-]*phone-actions\b[^>]*>/g;
  let match: RegExpExecArray | null;
  while ((match = open.exec(template))) {
    const block = elementAt(template, match.index);
    blocks.push(block);
    open.lastIndex = match.index + Math.max(block.length, 1);
  }
  return blocks;
}

/** Tira de um trecho os menus (`<XxxMenu …>`), onde o Atualizar é permitido. */
function withoutMenus(block: string): string {
  let out = block;
  const re = /<([A-Z][\w]*Menu)\b/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(out))) {
    const element = elementAt(out, match.index);
    out = out.slice(0, match.index) + out.slice(match.index + element.length);
    re.lastIndex = match.index;
  }
  return out;
}

/** Atualizar solto: o ícone `lucide:refresh-cw` ou o rótulo "Atualizar" fora de um menu. */
export function looseRefresh(block: string): boolean {
  const rest = withoutMenus(block);
  return /lucide:refresh-cw|(?:aria-label|label|title)="Atualizar"/.test(rest);
}

describe("guardrail da barra de cima do celular", () => {
  it("o detector pega o Atualizar solto e deixa passar o que mora no ⋯", () => {
    const solto = `<template><Cab><template #phone-actions>
      <button type="button" aria-label="Atualizar" @click="refresh()"><Icon name="lucide:refresh-cw" /></button>
      <PurchaseMoreMenu vertical :items="baseMenuItems" label="Mais: atualizar" />
    </template></Cab></template>`;
    const soltoComoIcone = `<template><Cab><template #phone-actions>
      <UiIconButton icon="lucide:refresh-cw" label="Atualizar" @click="refresh()" />
    </template></Cab></template>`;
    const noMenu = `<template><Cab><template #phone-actions>
      <template v-if="a"><PurchaseMoreMenu vertical :items="refreshMenuItems" label="Mais: atualizar" /></template>
      <MarketingPageMenu heading="Enviados" :items="MENU"><button aria-label="Atualizar" /></MarketingPageMenu>
    </template></Cab></template>`;
    const barraPropria = `<template><div data-hub-phone-actions><UiIconButton icon="lucide:refresh-cw" label="Atualizar" /></div></template>`;
    expect(phoneBarBlocks(solto).some(looseRefresh)).toBe(true);
    expect(phoneBarBlocks(soltoComoIcone).some(looseRefresh)).toBe(true);
    expect(phoneBarBlocks(barraPropria).some(looseRefresh)).toBe(true);
    expect(phoneBarBlocks(noMenu)).toHaveLength(1);
    expect(phoneBarBlocks(noMenu).some(looseRefresh)).toBe(false);
  });

  it("a varredura acha as barras dos apps (não passa por estar cega)", () => {
    const found = OPERATOR_SURFACES.flatMap((app) =>
      vueFiles(join(surfacesDir, app, "app")).filter((path) => phoneBarBlocks(readFileSync(path, "utf8")).length),
    );
    const rel = found.map((path) => relative(surfacesDir, path));
    expect(rel).toContain("purchase-nuxt/app/pages/index.vue");
  });

  it("nenhum app de operador põe Atualizar solto na barra de 56px (mora no ⋯)", () => {
    const offenders: string[] = [];
    for (const app of OPERATOR_SURFACES) {
      for (const path of vueFiles(join(surfacesDir, app, "app"))) {
        const blocks = phoneBarBlocks(readFileSync(path, "utf8"));
        if (blocks.some(looseRefresh)) offenders.push(relative(surfacesDir, path));
      }
    }
    expect(offenders).toEqual([]);
  });
});
