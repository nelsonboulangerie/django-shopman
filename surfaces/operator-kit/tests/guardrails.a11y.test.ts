import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Guardrail de NOME ACESSÍVEL: botão de ícone puro tem que dizer o que faz.
//
// Motivo medido: navegando o Marketing, a árvore de acessibilidade mostrava
// `button` sem rótulo nenhum. Não é caso, é CLASSE — a varredura achou os irmãos
// no kit (apagar dígito e continuar, no teclado de troca de PIN) e no PDV
// (atualizar as últimas vendas). Um botão sem nome é um botão que o leitor de
// tela anuncia como "botão", e o operador que depende dele fica adivinhando.
//
// A peça canônica é o `UiIconButton` do kit, que EXIGE `label` e devolve
// `aria-label` + `title`. Quando ele não serve (teclado numérico, botão dentro de
// um cabeçalho), `aria-label` resolve — o que não pode é ficar mudo.
//
// Storefront fica FORA: não estende esta layer (superfície de cliente, harness
// próprio). Mesma fronteira do `kitOwnership.guardrails`.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const SURFACES = [...OPERATOR_SURFACES, "operator-kit"].sort();

// A lista de exceções saiu junto com o `Ui/Switch.vue` do PDV (promovido ao kit
// como `UiSwitch`): ela era a única entrada, e era INERTE — a varredura só cobra
// nome de botão que tem `<Icon>` dentro, e o interruptor nunca teve ícone. Quem
// ficar sem nome por ser definição de primitivo já é atendido pela regra do
// `<slot>` abaixo: o conteúdo (e o nome) vêm de quem monta.

const NAMING_ATTRIBUTES = /aria-label|aria-labelledby|title=|\blabel=|:label\b/;

function vueFiles(dir: string, found: string[] = []): string[] {
  if (!existsSync(dir)) return found;
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".nuxt" || entry === ".output") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) vueFiles(full, found);
    else if (full.endsWith(".vue")) found.push(full);
  }
  return found;
}

/** Corpo de uma tag, respeitando aninhamento da MESMA tag. */
function readElement(source: string, start: number): { attrs: string; body: string } | null {
  const tag = /^<(\w+)/.exec(source.slice(start))?.[1];
  const openEnd = source.indexOf(">", start);
  if (!tag || openEnd < 0) return null;

  const attrs = source.slice(start, openEnd);
  if (attrs.trimEnd().endsWith("/")) return { attrs, body: "" };

  const boundary = new RegExp(`</?${tag}\\b`, "g");
  boundary.lastIndex = openEnd;
  let depth = 1;
  let match: RegExpExecArray | null;
  while ((match = boundary.exec(source))) {
    if (source.startsWith("</", match.index)) {
      depth -= 1;
      if (depth === 0) return { attrs, body: source.slice(openEnd + 1, match.index) };
    } else {
      const end = source.indexOf(">", match.index);
      if (end >= 0 && !source.slice(match.index, end).trimEnd().endsWith("/")) depth += 1;
    }
  }
  return null;
}

function mutePoints(file: string): number[] {
  const source = readFileSync(file, "utf8");
  const offenders: number[] = [];
  const buttons = /<(?:button|UiButton)\b/g;
  let match: RegExpExecArray | null;

  while ((match = buttons.exec(source))) {
    const element = readElement(source, match.index);
    if (!element || NAMING_ATTRIBUTES.test(element.attrs)) continue;
    if (!element.body.includes("<Icon")) continue;
    // `<slot>` = o conteúdo (e o nome) vem de quem monta.
    if (element.body.includes("<slot")) continue;

    const text = element.body
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/<[^>]*>/g, "")
      .trim();
    if (!text) offenders.push(source.slice(0, match.index).split("\n").length);
  }
  return offenders;
}

describe("superfícies de operador: botão de ícone puro tem nome", () => {
  for (const surface of SURFACES) {
    it(`${surface} não tem botão mudo`, () => {
      const offenders: string[] = [];
      for (const file of vueFiles(resolve(surfacesDir, surface, "app"))) {
        const relative = file.slice(surfacesDir.length + 1);
        for (const line of mutePoints(file)) offenders.push(`${relative}:${line}`);
      }

      expect(
        offenders,
        `Botão de ícone puro sem nome acessível (use <UiIconButton label="…"> ou ` +
          `aria-label; o leitor de tela anuncia "botão" e mais nada):\n  ` +
          offenders.join("\n  "),
      ).toEqual([]);
    });
  }
});
