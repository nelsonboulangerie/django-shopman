import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Guardrail de CÓPIA QUE NÃO SE CORTA — a metade estática da queixa do dono de
// 28/09/2026 ("tem copy estourando o espaço disponível… muito deselegante"). O
// caso-bandeira foi o "Dividir co…" no pagamento do PDV: `<span class="truncate">
// Dividir conta</span>`, rótulo FIXO de botão com reticências.
//
// A regra da casa: texto de AÇÃO e de AVISO não se corta. Botão que não cabe
// ganha rótulo mais curto (e inequívoco) ou quebra de linha; `truncate` só vale
// para DADO do usuário (nome de produto, endereço), com o texto inteiro no
// `title`. Texto escrito no template é, por construção, a voz da casa — então um
// elemento com `truncate`/`line-clamp-*`/`text-ellipsis` cujo conteúdo é literal
// (sem `{{ }}`) é sempre defeito, em qualquer largura.
//
// A metade AO VIVO — dado cortado sem `title`, coluna esmagada, aviso que passa
// da borda — é medida no navegador pela sonda `tests/support/clippedText.js`
// (PDV: `surfaces/pos-nuxt/tests/e2e-live/`). Esta aqui roda em todo CI.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const ROOTS = [...OPERATOR_SURFACES, "operator-kit"].map((dir) => join(surfacesDir, dir, "app"));
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);

/** Classe que CORTA texto (em qualquer variante responsiva). */
const CLIPS = /(?:^|[\s:])(?:truncate|text-ellipsis|line-clamp-\d)(?=\s|$)/;

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

function template(source: string): string {
  const start = source.indexOf("<template");
  const end = source.lastIndexOf("</template>");
  return start >= 0 && end > start ? source.slice(start, end) : "";
}

/** O texto direto até a próxima tag — pulando `<` dentro de `{{ }}` (`a < b`). */
function directText(after: string): string {
  let depth = 0;
  let end = after.length;
  for (let i = 0; i < after.length; i += 1) {
    if (after.startsWith("{{", i)) { depth += 1; i += 1; continue; }
    if (after.startsWith("}}", i)) { depth = Math.max(0, depth - 1); i += 1; continue; }
    if (after[i] === "<" && depth === 0) { end = i; break; }
  }
  return after.slice(0, end).replace(/\s+/g, " ").trim();
}

/** Elementos que cortam texto e cujo conteúdo DIRETO é texto escrito no template. */
export function literalClipped(source: string): Array<{ line: number; text: string }> {
  const tpl = template(source);
  const offset = source.indexOf(tpl);
  const found: Array<{ line: number; text: string }> = [];
  // Uma tag de abertura com `class="..."` estático (a dinâmica `:class` também
  // conta: `truncate` ligado por condição corta do mesmo jeito).
  const tag = /<([a-zA-Z][\w-]*)\b([^<>]*?)>/g;
  for (let match = tag.exec(tpl); match; match = tag.exec(tpl)) {
    const attrs = match[2] ?? "";
    const classes = [...attrs.matchAll(/(?::class|class)="([^"]*)"/g)].map((m) => m[1] ?? "").join(" ");
    if (!CLIPS.test(classes)) continue;
    if (attrs.trimEnd().endsWith("/")) continue;
    const after = tpl.slice(match.index + match[0].length);
    const content = directText(after);
    // Só dado ({{ produto.nome }}) pode cortar. Texto escrito em volta do dado
    // ("Capacidade · {{ nível }}") é voz da casa, e corta junto.
    const literal = content.replace(/\{\{[\s\S]*?\}\}/g, " ").replace(/[·•|,:()\-–—]/g, " ");
    if (!/[A-Za-zÀ-ú]{2,}/.test(literal)) continue;
    const line = source.slice(0, offset + match.index).split("\n").length;
    found.push({ line, text: content });
  }
  return found;
}

describe("cópia da casa não se corta", () => {
  it("a regra reconhece o caso-bandeira e deixa passar o dado do usuário", () => {
    const sample = `<template>
      <span class="min-w-0 flex-1 truncate text-left">Dividir conta</span>
      <span class="truncate" :title="product.name">{{ product.name }}</span>
      <span class="min-w-0 truncate text-sm">Capacidade · {{ meta.label }}</span>
      <p class="line-clamp-2">
        Ao finalizar, o item vai para a cozinha.
      </p>
    </template>`;
    expect(literalClipped(sample).map((f) => f.text)).toEqual([
      "Dividir conta",
      "Capacidade · {{ meta.label }}",
      "Ao finalizar, o item vai para a cozinha.",
    ]);
  });

  it("nenhum template de operador corta texto escrito nele", () => {
    const offenders: string[] = [];
    for (const root of ROOTS) {
      for (const file of vueFiles(root)) {
        for (const hit of literalClipped(readFileSync(file, "utf8"))) {
          offenders.push(`${relative(surfacesDir, file)}:${hit.line} — "${hit.text}"`);
        }
      }
    }
    expect(offenders, [
      "Rótulo e aviso escritos no template não levam truncate/line-clamp/text-ellipsis.",
      "Encurte o rótulo (sem abreviação críptica) ou deixe quebrar a linha.",
      ...offenders,
    ].join("\n")).toEqual([]);
  });
});
