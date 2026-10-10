import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Trava do CONJUNTO MÍNIMO da suíte (dono, 08/10/2026, PR #1539; laudo em
// docs/plans/WP-BI-CANON-LAUDO.md, seção F). O tema do kit fixa o default de cada
// peça; esta trava conta o que foge do conjunto escrito na chamada e só deixa a
// conta CAIR. Cada número abaixo é o que existia quando o conjunto foi aprovado:
// migrar um uso baixa o teto (atualize o número para o novo valor); um uso NOVO fora
// do conjunto reprova. O conjunto, peça por peça, está no README do kit, seção
// "Conjunto mínimo da suíte".
//
//   botão   tamanho md|xl · variante solid|outline|ghost · cor primary|neutral|error
//   selo    sem `variant` escrito (o tema dá `soft`)
//   cartão  `outline` (default) ou `soft` (dentro de outro cartão); nunca subtle/solid
//   aviso   `subtle` × info|success|warning|error
//   texto   nenhum tamanho arbitrário (`text-[13px]`, `text-[0.625rem]`)
//
// Exceção declarada (dono, 08/10/2026, PR #1545): a AÇÃO DE AVISO repete a cor do
// aviso. Botão dentro de um `NuxtAlert` (slot `#actions`, `#description`…) com cor
// info|success|warning|error não conta em `buttonColor`, desde que seja a cor do
// próprio aviso (se a cor do aviso é ligada, qualquer cor de aviso passa). Motivo: o
// botão é a saída daquele aviso, e neutro ele se descola do estado que o chamou. As
// ações declaradas em objeto no prop `actions` do aviso nem chegam a esta conta (não
// são tag `NuxtButton`), e seguem a mesma regra.
//
// Prop ligada (`:variant="…"`) não é julgada aqui, exceto no selo, onde qualquer
// `variant` é desvio. A contagem é por regex sobre a tag de abertura: piso, não censo.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);

type Rule =
  | "buttonSize"
  | "buttonVariant"
  | "buttonColor"
  | "badgeVariant"
  | "cardVariant"
  | "alertOutsideSet"
  | "arbitraryTextSize";

// Teto por diretório (medido em 08/10/2026 sobre a base do PR-K3). Diretório
// ausente = teto zero em todas as regras.
const CEILING: Record<string, Partial<Record<Rule, number>>> = {
  "operator-kit": {
    buttonSize: 9,
    buttonVariant: 14,
    // `buttonColor` caiu para zero com a exceção da ação de aviso: os dois `warning`
    // que sobravam são as ações do aviso de descarte do `OperatorReasonDialog`.
    badgeVariant: 12,
    cardVariant: 1,
    alertOutsideSet: 19,
    // Inclui duas exceções declaradas: o chip `4xl` (`text-[12px]/none` no
    // app.config) e o rótulo da barra inferior (`text-[10px]/3` em `presentation/tabBar.ts`, o desenho das duas barras de baixo),
    // que é o valor do exemplo oficial "With bottom tab bar" do NavigationMenu (dono,
    // 08/10/2026, PR #1544).
    arbitraryTextSize: 12,
  },
  // Gestor na passada de conformidade (08/10/2026). Sobra um, de propósito: a pílula
  // de aviso do cartão (`OrderCard`, `xs` `soft` na cor do aviso), sinal de estado a
  // um toque do Popover; neutra, apagaria a cor lida de longe. As ações de aviso
  // ("Copiar endereço", "Manter sem GTIN na nota", "Aplicar meu arraste…") são a
  // exceção declarada acima e não contam.
  "orders-nuxt": {
    buttonSize: 1,
    buttonVariant: 1,
  },
  "pos-nuxt": { arbitraryTextSize: 7 },
  "production-nuxt": { arbitraryTextSize: 8 },
};

const BUTTON_SIZES = new Set(["md", "xl"]);
const BUTTON_VARIANTS = new Set(["solid", "outline", "ghost"]);
const BUTTON_COLORS = new Set(["primary", "neutral", "error"]);
const CARD_VARIANTS = new Set(["outline", "soft"]);
const ALERT_COLORS = new Set(["info", "success", "warning", "error"]);
const ARBITRARY_TEXT = /\btext-\[\d+(?:\.\d+)?(?:px|rem|em)\]/g;

function sourceFiles(dir: string, found: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return found;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (full.endsWith(".vue") || full.endsWith(".ts")) found.push(full);
  }
  return found;
}

/** Atributos das tags de abertura `<Tag …>`. */
function openingTags(source: string, tag: string): string[] {
  return openingTagsAt(source, tag).map((tagAt) => tagAt.attrs);
}

/** Atributos e posição das tags de abertura `<Tag …>`. */
function openingTagsAt(source: string, tag: string): { attrs: string; at: number }[] {
  const pattern = new RegExp(`<${tag}(?![\\w-])([^>]*?)/?>`, "gs");
  return [...source.matchAll(pattern)].map((match) => ({
    attrs: match[1] ?? "",
    at: match.index ?? 0,
  }));
}

/**
 * Trechos `<NuxtAlert …>…</NuxtAlert>` com as cores que a ação pode repetir: a cor
 * literal do aviso, ou todas as de aviso quando a cor é ligada.
 */
function alertBodies(source: string): { from: number; to: number; colors: Set<string> }[] {
  const bodies: { from: number; to: number; colors: Set<string> }[] = [];
  for (const match of source.matchAll(/<NuxtAlert(?![\w-])/g)) {
    // Fim da tag de abertura fora de aspas: `:actions="[{ onClick: () => … }]"` tem `>`.
    let end = (match.index ?? 0) + match[0].length;
    let quote = "";
    for (; end < source.length; end += 1) {
      const char = source[end];
      if (quote) {
        if (char === quote) quote = "";
      } else if (char === '"' || char === "'") quote = char;
      else if (char === ">") break;
    }
    const attrs = source.slice((match.index ?? 0) + match[0].length, end);
    if (attrs.trimEnd().endsWith("/")) continue;
    const to = source.indexOf("</NuxtAlert>", end);
    if (to < 0) continue;
    const color = prop(attrs, "color");
    const colors = color?.literal !== undefined ? new Set([color.literal]) : ALERT_COLORS;
    bodies.push({ from: end, to, colors });
  }
  return bodies;
}

/** A ação de aviso que repete a cor do aviso (exceção declarada no topo). */
function alertAction(bodies: ReturnType<typeof alertBodies>, at: number, attrs: string): boolean {
  const color = prop(attrs, "color")?.literal;
  if (color === undefined || !ALERT_COLORS.has(color)) return false;
  return bodies.some((body) => at > body.from && at < body.to && body.colors.has(color));
}

/** `literal` para `prop="x"`, `bound` para `:prop="…"`, `null` se ausente. */
function prop(attrs: string, name: string): { literal?: string; bound?: true } | null {
  const match = attrs.match(new RegExp(`(?:^|\\s)(:|v-bind:)?${name}="([^"]*)"`));
  if (!match) return null;
  return match[1] ? { bound: true } : { literal: match[2] };
}

function outside(attrs: string, name: string, allowed: Set<string>): boolean {
  const value = prop(attrs, name);
  return Boolean(value?.literal !== undefined && !allowed.has(value.literal));
}

function count(dir: string): Record<Rule, number> {
  const totals: Record<Rule, number> = {
    buttonSize: 0,
    buttonVariant: 0,
    buttonColor: 0,
    badgeVariant: 0,
    cardVariant: 0,
    alertOutsideSet: 0,
    arbitraryTextSize: 0,
  };
  for (const file of sourceFiles(join(surfacesDir, dir, "app"))) {
    const source = readFileSync(file, "utf8");
    totals.arbitraryTextSize += (source.match(ARBITRARY_TEXT) ?? []).length;
    if (!file.endsWith(".vue")) continue;
    const alerts = alertBodies(source);
    for (const { attrs, at } of openingTagsAt(source, "NuxtButton")) {
      if (outside(attrs, "size", BUTTON_SIZES)) totals.buttonSize += 1;
      if (outside(attrs, "variant", BUTTON_VARIANTS)) totals.buttonVariant += 1;
      if (outside(attrs, "color", BUTTON_COLORS) && !alertAction(alerts, at, attrs)) {
        totals.buttonColor += 1;
      }
    }
    for (const attrs of openingTags(source, "NuxtBadge")) {
      if (prop(attrs, "variant")) totals.badgeVariant += 1;
    }
    for (const attrs of openingTags(source, "NuxtCard")) {
      if (outside(attrs, "variant", CARD_VARIANTS)) totals.cardVariant += 1;
    }
    for (const attrs of openingTags(source, "NuxtAlert")) {
      const variant = prop(attrs, "variant");
      const wrongVariant = !variant || (variant.literal !== undefined && variant.literal !== "subtle");
      if (wrongVariant || outside(attrs, "color", ALERT_COLORS)) totals.alertOutsideSet += 1;
    }
  }
  return totals;
}

describe("conjunto mínimo da suíte: nenhum uso novo fora do conjunto", () => {
  for (const dir of [...OPERATOR_SURFACES, "operator-kit"]) {
    it(`${dir} não passa do teto de nenhuma regra`, () => {
      const current = count(dir);
      const ceiling = CEILING[dir] ?? {};
      const over = (Object.keys(current) as Rule[])
        .filter((rule) => current[rule] > (ceiling[rule] ?? 0))
        .map((rule) => `${rule}: ${current[rule]} (teto ${ceiling[rule] ?? 0})`);
      expect(over, `${dir} saiu do conjunto mínimo; ver README do kit`).toEqual([]);
    });
  }
});
