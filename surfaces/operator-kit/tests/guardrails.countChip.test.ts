import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Trava do CHIP DE CONTAGEM da suíte (dono, 09/10/2026). Toda contagem mora no
// `OperatorCountChip` (no fluxo: botão, aba, recorte, barra lateral aberta) ou no
// `chip` de um item do NavigationMenu por `countChipProps` (no canto do ícone: barra
// compactada, barra inferior). O contador em retângulo arredondado não volta:
//
//   numericBadge   `NuxtBadge`/`UBadge` cujo rótulo é só um número
//                  (`:label="String(x)"`, `:label="lista.length"`, `{{ n }}` no corpo)
//   itemBadge      item de aba/menu com `badge:` numérico (o Tabs e o NavigationMenu
//                  desenham `badge` como selo de cantos arredondados)
//   roundedCounter número escrito à mão numa caixa de cantos não redondos
//                  (`rounded-md` e companhia + `tabular-nums` em volta de `{{ … }}`)
//
// Rótulo com palavra ("3 pedidos", "Incompleto") é selo, não contador, e passa.
// Nenhuma exceção hoje: uma nova entra aqui com motivo, arquivo por arquivo.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);

const EXCEPTIONS: Readonly<Record<string, string>> = {};

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

/** Expressão que é só uma contagem: `x.length`, `fooCount`, `counts.all`, `String(n)`. */
const COUNT_EXPRESSION =
  /^\s*(?:String\(\s*)?[\w.?$[\]'"]*?(?:\.length|[cC]ount[s]?\b[\w.?[\]'"]*|Count\b)\s*\)?\s*$/;

function isCountExpression(expression: string): boolean {
  return COUNT_EXPRESSION.test(expression) || /^\s*String\([^`]*\)\s*$/.test(expression);
}

function countChipViolations(source: string): string[] {
  const found: string[] = [];
  // numericBadge: rótulo ligado que é só número, ou corpo `{{ … }}` só de número.
  for (const match of source.matchAll(/<(NuxtBadge|UBadge)(?![\w-])([^>]*?)(\/?)>/gs)) {
    const attrs = match[2] ?? "";
    const label = attrs.match(/:label="([^"]*)"/);
    if (label && isCountExpression(label[1]!)) {
      found.push(`numericBadge: <${match[1]} :label="${label[1]}">`);
      continue;
    }
    if (match[3] !== "/") {
      const rest = source.slice((match.index ?? 0) + match[0].length);
      const body = rest.match(new RegExp(`^\\s*\\{\\{([^}]*)\\}\\}\\s*</${match[1]}>`));
      if (body && isCountExpression(body[1]!)) found.push(`numericBadge: <${match[1]}>{{${body[1]}}}`);
    }
  }
  // itemBadge: `badge: <contagem>` num item (Tabs, NavigationMenu, DropdownMenu). Só
  // onde o arquivo desenha uma dessas peças: o `badge` de uma `OperatorSection` é a
  // contagem que a barra lateral transforma em chip, e passa.
  const drawsItemBadges = /<(?:Nuxt|U)(?:Tabs|NavigationMenu|DropdownMenu|CommandPalette)(?![\w-])/.test(source);
  for (const match of drawsItemBadges ? source.matchAll(/\bbadge:\s*([^,\n}]+)/g) : []) {
    // Aqui vale também o número que chega de outro campo (`badge: section.badge`):
    // o `badge` da seção é a contagem dela.
    const value = match[1]!;
    if (isCountExpression(value) || /String\(|\.length\b|\.badge\b/.test(value)) {
      found.push(`itemBadge: badge: ${value.trim()}`);
    }
  }
  // roundedCounter: `{{ contagem }}` numa caixa de cantos não inteiramente redondos.
  for (const match of source.matchAll(/<(span|div|p)\s[^>]*class="([^"]*)"[^>]*>\s*\{\{([^}]*)\}\}\s*<\/\1>/g)) {
    const classes = match[2]!.split(/\s+/);
    const squareCorners = classes.some((name) => /^rounded(?:-(?:xs|sm|md|lg|xl))?$/.test(name));
    if (squareCorners && classes.includes("tabular-nums") && isCountExpression(match[3]!)) {
      found.push(`roundedCounter: {{${match[3]}}}`);
    }
  }
  return found;
}

describe("chip de contagem: nenhum contador em retângulo arredondado", () => {
  it("a regra reconhece o contador antigo e deixa passar o selo com palavra", () => {
    expect(countChipViolations('<NuxtBadge color="neutral" :label="String(cards.length)" />')).toHaveLength(1);
    expect(countChipViolations('<UBadge :label="activeCount" />')).toHaveLength(1);
    expect(countChipViolations("<NuxtBadge>{{ items.length }}</NuxtBadge>")).toHaveLength(1);
    const tabs = "<NuxtTabs :items=\"items\" />\n";
    expect(countChipViolations(`${tabs}{ value: 'all', label: 'Todos', badge: rows.value.length }`)).toHaveLength(1);
    expect(countChipViolations(`${tabs}badge: String(collection.product_count),`)).toHaveLength(1);
    expect(countChipViolations("{ key: 'receive', badge: String(receivePending.value) }")).toEqual([]);
    expect(
      countChipViolations('<span class="rounded-md px-1 tabular-nums">{{ pendingCount }}</span>'),
    ).toHaveLength(1);
    expect(countChipViolations('<NuxtBadge :label="`${n} pedidos`" />')).toEqual([]);
    expect(countChipViolations('badge: row.pim_complete ? undefined : "Incompleto",')).toEqual([]);
    expect(countChipViolations(`${tabs}badge: "badge" in item ? item.badge : undefined,`)).toHaveLength(1);
    expect(countChipViolations("badge: entry.attention || undefined,")).toEqual([]);
    expect(countChipViolations('<OperatorCountChip :count="cards.length" />')).toEqual([]);
  });

  it("o chip é UM componente, sobre o NuxtChip canônico", () => {
    const component = readFileSync(join(surfacesDir, "operator-kit/app/components/OperatorCountChip.vue"), "utf8");
    expect(component).toMatch(/<NuxtChip\b/);
    expect(component).toContain("countChipText");
  });

  for (const dir of [...OPERATOR_SURFACES, "operator-kit"]) {
    it(`${dir} conta só com o chip de contagem`, () => {
      const offenders: string[] = [];
      for (const file of vueFiles(join(surfacesDir, dir, "app"))) {
        const path = relative(surfacesDir, file);
        if (EXCEPTIONS[path]) continue;
        for (const violation of countChipViolations(readFileSync(file, "utf8"))) {
          offenders.push(`${path}: ${violation}`);
        }
      }
      expect(offenders, "contagem é `OperatorCountChip` (README do kit, \"Chip de contagem\")").toEqual([]);
    });
  }
});
