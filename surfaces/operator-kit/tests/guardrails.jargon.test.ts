import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Guardrail de JARGÃO: a tela do operador fala a língua da padaria, não a de quem
// construiu o sistema. É o defeito D7a de `docs/reference/omotenashi-copy.md`
// ("termo interno vazado"), e a régua é a do teste de uma frase: o leitor precisou
// lembrar de algo que a tela não mostra? "Core", "backend", "endpoint" e "SSE" são
// exatamente isso, e "o servidor não montou o comprovante" é a nota de rodapé do
// engenheiro (D6) no lugar do que aconteceu.
//
// ## De onde veio
//
// Em 09/10/2026 o dono leu "Conectando ao Core de compras" no carregamento do Compras
// e pediu a varredura com trava. A frase tinha passado por várias revisões de copy,
// porque nenhuma regra dizia que "Core" não é palavra de tela: as quatro travas de
// vocabulário (`guardrails.vocabulary.test.ts`) cobram palavras da casa, não palavras
// de fora dela. Esta cobra as de fora.
//
// ## O que conta como texto de tela
//
// O que pode chegar ao operador: o texto entre as tags do `<template>`, o valor dos
// atributos estáticos (rótulo, título, `aria-label`, placeholder), os literais dentro
// das ligações dinâmicas (`:label="'…'"`, `{{ cond ? '…' : '…' }}`) e os literais de
// script que parecem frase (têm espaço). Comentário é descontado, como na regra do
// "lote": explicar ao programador que "o servidor recalcula o peso" continua certo.
// Identificador também fica de fora sozinho: `backendReady`, `payload.queue` e
// `OPERATOR_PERM = "cashman.operate_pos"` não são literal com espaço nem texto de tag.
//
// ## Quem fica de fora, e por quê
//
//   - **storefront-nuxt**: a loja é superfície de cliente e tem a sua revisão própria.
//   - **Kitchen Sink** (`kitchensink-nuxt/` e o catálogo dentro do kit): o leitor é
//     quem desenha a suíte, e o assunto da página é justamente o Nuxt UI e os tokens.
//   - **`server/`** (o BFF): as mensagens dali são do deploy e do log; o que chega à
//     tela passa pelo `httpError` do kit, que já fala português.
//
// ⚠️ "projeção", em português, NÃO é recusada: é o nome da tela de previsão do B.I.
// (Projeção, "dias parecidos do passado"), palavra de negócio. Recusada é a
// `projection` em inglês. E "sincronização" com as plataformas (iFood, Instagram)
// também fica: é o gesto que o gestor faz com a plataforma, não detalhe interno.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Cada termo, com o que dizer no lugar. A trava não troca sozinha: leia a linha. */
const JARGON: ReadonlyArray<{ pattern: RegExp; hint: string }> = [
  { pattern: /\bCore\b/, hint: "diga o que carrega: 'as compras', 'o pedido'" },
  { pattern: /\bback-?end\b/i, hint: "diga o que não carregou, e o gesto para tentar de novo" },
  { pattern: /\bAPI\b/, hint: "nomeie a plataforma ou o que ela faz" },
  { pattern: /\bendpoints?\b/i, hint: "diga o que não respondeu" },
  { pattern: /\bpayloads?\b/i, hint: "diga o que foi enviado" },
  { pattern: /\bprojection\b/i, hint: "diga o que a tela mostra" },
  { pattern: /\bSSE\b/, hint: "'ao vivo'" },
  { pattern: /\btokens?\b/i, hint: "'código', 'chave', 'acesso'" },
  { pattern: /\bwebhooks?\b/i, hint: "diga quem avisou o quê" },
  { pattern: /\b(?:Django|Nuxt|BFF|JSON|HTTP)\b/, hint: "o operador não sabe com que o sistema foi feito" },
  {
    pattern: /\b(?:offerman|stockman|craftsman|orderman|guestman|doorman|payman|buyman|fiscalman|cashman)\b/i,
    hint: "nome de pacote: diga Catálogo, Estoque, Produção, Pedidos, Clientes, Caixa",
  },
  { pattern: /\bservidor\b/i, hint: "diga o que aconteceu ('não ficou pronto', 'mudou enquanto você editava')" },
  { pattern: /\bdirectives?\b/i, hint: "'tarefa'" },
];

const SKIP_DIRS = new Set([
  "node_modules",
  ".nuxt",
  ".output",
  "dist",
  "coverage",
  "test-results",
  "playwright-report",
  "blob-report",
  "tests",
  "server",
  "public",
]);

const APPS = [...OPERATOR_SURFACES, "operator-kit"].filter((app) => app !== "kitchensink-nuxt");

/** O catálogo do Kitchen Sink mora também dentro do kit; o leitor dele é quem desenha. */
const isKitchenSink = (path: string) => /kitchen-?sink/i.test(path);

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (/\.(vue|ts)$/.test(full) && !/\.d\.ts$/.test(full)) found.push(full);
  }
  return found;
}

const SOURCES = APPS.flatMap((app) => {
  const appDir = join(surfacesDir, app, "app");
  try {
    statSync(appDir);
  } catch {
    return [];
  }
  return sourceFiles(appDir);
}).filter((file) => !isKitchenSink(relative(surfacesDir, file)));

const blank = (chunk: string) => chunk.replace(/[^\n]/g, " ");

/** Apaga comentário preservando as quebras de linha (o `//` de `https://` fica). */
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, (match, prefix: string) => prefix + blank(match.slice(prefix.length)));
}

interface Snippet {
  offset: number;
  text: string;
}

const LITERAL = /(["'`])((?:\\.|(?!\1)[^\\])*?)\1/gs;

/** Literais de código que parecem frase: têm espaço e letra, e não são caminho. */
function proseLiterals(code: string, base: number): Snippet[] {
  const found: Snippet[] = [];
  for (const match of code.matchAll(LITERAL)) {
    // O que vai dentro de `${…}` é código (`payload.queue`), não texto.
    const value = (match[2] ?? "").replace(/\$\{[^}]*\}/g, " ");
    if (!/\s/.test(value.trim()) || !/\p{L}/u.test(value)) continue;
    if (/^\s*(?:\/|https?:)/.test(value)) continue;
    found.push({ offset: base + (match.index ?? 0), text: value });
  }
  return found;
}

/** Atributos estáticos que nunca são texto (classe, ícone, rota, chave). */
const NON_TEXT_ATTRS = /^(?:class|icon|trailing-icon|leading-icon|to|href|src|name|id|key|ref|type|role|for|as|variant|color|size|side|align|mode|inputmode|autocomplete|data-[\w-]+)$/;

function templateSnippets(template: string, base: number): Snippet[] {
  const found: Snippet[] = [];
  let rest = template;
  // Ligações dinâmicas: o valor é código; dele só contam os literais.
  rest = rest.replace(
    /(\s)((?:[:@#]|v-)[\w.:[\]-]*)="([^"]*)"/g,
    (match, space: string, _name: string, value: string, index: number) => {
      const valueStart = index + match.indexOf('="') + 2;
      found.push(...proseLiterals(value, base + valueStart));
      return space + blank(match.slice(space.length));
    },
  );
  rest = rest.replace(/\{\{([\s\S]*?)\}\}/g, (match, inner: string, index: number) => {
    found.push(...proseLiterals(inner, base + index + 2));
    return blank(match);
  });
  rest = rest.replace(/(\s)([\w-]+)="([^"]*)"/g, (match, space: string, name: string, value: string, index: number) => {
    if (!NON_TEXT_ATTRS.test(name) && /\p{L}/u.test(value)) {
      found.push({ offset: base + index + match.indexOf('="') + 2, text: value });
    }
    return space + blank(match.slice(space.length));
  });
  rest = rest.replace(/<[^>]*>/g, blank);
  for (const match of rest.matchAll(/[^\n]*\p{L}[^\n]*/gu)) {
    found.push({ offset: base + (match.index ?? 0), text: match[0] });
  }
  return found;
}

function screenSnippets(file: string): Snippet[] {
  const text = stripComments(readFileSync(file, "utf8"));
  if (!file.endsWith(".vue")) return proseLiterals(text, 0);
  const found: Snippet[] = [];
  const templateOpen = text.indexOf("<template");
  const templateClose = text.lastIndexOf("</template>");
  for (const match of text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)) {
    const start = (match.index ?? 0) + match[0].indexOf(">") + 1;
    found.push(...proseLiterals(match[1] ?? "", start));
  }
  if (templateOpen >= 0 && templateClose > templateOpen) {
    const bodyStart = text.indexOf(">", templateOpen) + 1;
    found.push(...templateSnippets(text.slice(bodyStart, templateClose), bodyStart));
  }
  return found;
}

function lineOf(text: string, offset: number): number {
  return text.slice(0, offset).split("\n").length;
}

function leaks(): string[] {
  const out: string[] = [];
  for (const file of SOURCES) {
    const raw = readFileSync(file, "utf8");
    for (const snippet of screenSnippets(file)) {
      const hit = JARGON.find(({ pattern }) => pattern.test(snippet.text));
      if (!hit) continue;
      out.push(
        `${relative(surfacesDir, file)}:${lineOf(raw, snippet.offset)}: "${snippet.text.trim().slice(0, 120)}" → ${hit.hint}`,
      );
    }
  }
  return out;
}

describe("a tela do operador fala a língua da padaria, não a do sistema", () => {
  it("nenhum texto de operador usa jargão técnico", () => {
    const found = leaks();
    expect(
      found,
      "Termo interno na tela do operador (D7a de docs/reference/omotenashi-copy.md).\n" +
        "Reescreva dizendo o que aconteceu e o que fazer, na voz da casa. Se a frase\n" +
        "começa explicando o sistema, o defeito é D6: apague a explicação e veja o\n" +
        `que sobra.\nOnde:\n  ${found.join("\n  ")}`,
    ).toEqual([]);
  }, 30_000);

  it("a varredura enxerga os apps de operador e o kit", () => {
    const apps = new Set(SOURCES.map((file) => relative(surfacesDir, file).split("/")[0]));
    expect([...apps].sort()).toEqual(APPS.slice().sort());
    expect(SOURCES.length).toBeGreaterThan(400);
  });

  // A trava enxerga o caso que a criou: se a extração de texto quebrar, este cai antes.
  it("reconhece texto de tag, atributo, ligação dinâmica e literal de script", () => {
    const sample = [
      "<script setup>",
      'const a = "Conecte o backend para salvar.";',
      "</script>",
      "<template>",
      "  <span>Conectando ao Core de compras</span>",
      '  <UButton label="Abrir o endpoint" :title="ok ? \'Sem SSE agora\' : \'\'" />',
      "  <p>{{ busy ? 'O servidor não respondeu' : '' }}</p>",
      "  <!-- o servidor decide: comentário não conta -->",
      "</template>",
    ].join("\n");
    const base = 0;
    const text = stripComments(sample);
    const templateOpen = text.indexOf("<template");
    const bodyStart = text.indexOf(">", templateOpen) + 1;
    const snippets = [
      ...proseLiterals(text.slice(0, templateOpen), base),
      ...templateSnippets(text.slice(bodyStart, text.lastIndexOf("</template>")), bodyStart),
    ].filter((snippet) => JARGON.some(({ pattern }) => pattern.test(snippet.text)));
    expect(snippets.map((snippet) => lineOf(sample, snippet.offset)).sort()).toEqual([2, 5, 6, 6, 7]);
  });
});
