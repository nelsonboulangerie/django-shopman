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
    buttonColor: 2,
    badgeVariant: 12,
    cardVariant: 1,
    alertOutsideSet: 19,
    // Inclui duas exceções declaradas: o chip `4xl` (`text-[12px]/none` no
    // app.config) e o rótulo da barra inferior (`text-[10px]/3` no `OperatorQuickBar`),
    // que é o valor do exemplo oficial "With bottom tab bar" do NavigationMenu (dono,
    // 08/10/2026, PR #1544).
    arbitraryTextSize: 12,
  },
  "orders-nuxt": {
    buttonSize: 12,
    buttonVariant: 13,
    buttonColor: 5,
    badgeVariant: 54,
    cardVariant: 2,
    alertOutsideSet: 15,
  },
  "marketing-nuxt": { arbitraryTextSize: 63 },
  "pos-nuxt": { arbitraryTextSize: 7 },
  "production-nuxt": { arbitraryTextSize: 8 },
  "purchase-nuxt": { arbitraryTextSize: 19 },
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
  const pattern = new RegExp(`<${tag}(?![\\w-])([^>]*?)/?>`, "gs");
  return [...source.matchAll(pattern)].map((match) => match[1] ?? "");
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
    for (const attrs of openingTags(source, "NuxtButton")) {
      if (outside(attrs, "size", BUTTON_SIZES)) totals.buttonSize += 1;
      if (outside(attrs, "variant", BUTTON_VARIANTS)) totals.buttonVariant += 1;
      if (outside(attrs, "color", BUTTON_COLORS)) totals.buttonColor += 1;
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
