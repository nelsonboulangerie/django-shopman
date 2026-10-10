import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { alertActions } from "../app/utils/alertActions";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// A ação dentro de um aviso acompanha a cor do aviso (dono, 09/10/2026): a principal é
// `solid` na cor do aviso, a secundária `outline` na mesma cor. Nunca um `primary` ou
// `neutral` "normal" dentro de um aviso info/warning/error/success.
//
// A trava lê os `.vue` do kit e dos apps de operador e reprova:
//   - `NuxtAlert`/`UAlert` com `:actions` que não passa por `alertActions(<cor do aviso>, …)`;
//   - botão no slot `#actions` do aviso com `color` diferente da do aviso.
//
// ⚠️ Lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");

function vueFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "node_modules" || entry.name.startsWith(".") ? [] : vueFiles(path);
    }
    return entry.name.endsWith(".vue") ? [path] : [];
  });
}

/** O fim da tag de abertura, respeitando aspas (atributo com `>` dentro de expressão). */
function openingTagEnd(source: string, start: number): number {
  let quote = "";
  for (let i = start; i < source.length; i += 1) {
    const char = source[i]!;
    if (quote) {
      if (char === quote) quote = "";
    } else if (char === '"' || char === "'") {
      quote = char;
    } else if (char === ">") {
      return i;
    }
  }
  return source.length;
}

function attribute(tag: string, name: string): { value: string; bound: boolean } | null {
  const bound = new RegExp(`\\s:${name}="([^"]*)"`, "s").exec(tag);
  if (bound) return { value: bound[1]!.trim(), bound: true };
  const plain = new RegExp(`\\s${name}="([^"]*)"`).exec(tag);
  if (plain) return { value: plain[1]!.trim(), bound: false };
  return null;
}

/** A cor do aviso como ela deve aparecer no 1º argumento de `alertActions`. */
function expectedColorArgs(color: { value: string; bound: boolean } | null): string[] {
  if (!color) return ["undefined"];
  if (color.bound) return [color.value];
  return [`'${color.value}'`, `"${color.value}"`];
}

export function alertActionProblems(source: string): string[] {
  const problems: string[] = [];
  const pattern = /<(NuxtAlert|UAlert)\b/g;
  for (let match = pattern.exec(source); match; match = pattern.exec(source)) {
    const end = openingTagEnd(source, match.index);
    const tag = source.slice(match.index, end + 1);
    const line = source.slice(0, match.index).split("\n").length;
    const color = attribute(tag, "color");
    const actions = /\s:actions="([^"]*)"/s.exec(tag);
    if (actions) {
      const expression = actions[1]!.trim();
      const call = /^alertActions\(\s*([^,]+?)\s*,/s.exec(expression);
      if (!call) {
        problems.push(`linha ${line}: \`:actions\` sem \`alertActions(<cor do aviso>, …)\``);
      } else if (!expectedColorArgs(color).includes(call[1]!)) {
        problems.push(`linha ${line}: \`alertActions(${call[1]}, …)\` num aviso de cor ${color?.value ?? "padrão"}`);
      }
    }
    if (tag.endsWith("/>")) continue;
    const close = source.indexOf(`</${match[1]}>`, end);
    const body = source.slice(end + 1, close < 0 ? undefined : close);
    const slot = /<template\s+#actions\s*>([\s\S]*?)<\/template>/.exec(body);
    if (!slot) continue;
    const buttons = /<(NuxtButton|UButton|OperatorTimedButton)\b/g;
    for (let button = buttons.exec(slot[1]!); button; button = buttons.exec(slot[1]!)) {
      const buttonTag = slot[1]!.slice(button.index, openingTagEnd(slot[1]!, button.index) + 1);
      const buttonColor = attribute(buttonTag, "color");
      const same =
        buttonColor && color && buttonColor.value === color.value && buttonColor.bound === color.bound;
      if (!same) {
        problems.push(
          `linha ${line}: botão do \`#actions\` com cor ${buttonColor?.value ?? "padrão"} num aviso de cor ${color?.value ?? "padrão"}`,
        );
      }
    }
  }
  return problems;
}

/**
 * Dívida conhecida, corrigida no PR de apps logo depois deste (a varredura passou de 15
 * arquivos de app). Só pode encolher: arquivo que sai daqui não volta, e arquivo novo
 * nasce na regra.
 */
const KNOWN_APP_DEBT: Readonly<Record<string, number>> = {};

describe("ação dentro de aviso acompanha a cor do aviso", () => {
  it("alertActions: principal solid, secundária outline, as duas na cor do aviso, em md", () => {
    const [main, other] = alertActions("warning", [
      { label: "Ver os atrasados" },
      { label: "Agora não" },
    ]);
    expect(main).toMatchObject({ color: "warning", variant: "solid", size: "md" });
    expect(other).toMatchObject({ color: "warning", variant: "outline", size: "md" });
    const [later, install] = alertActions("info", [
      { label: "Agora não", secondary: true },
      { label: "Instalar", secondary: false },
    ]);
    expect(later).toMatchObject({ color: "info", variant: "outline" });
    expect(install).toMatchObject({ color: "info", variant: "solid" });
    // A cor e a variante são do aviso: a chamada não as escolhe.
    expect(alertActions("error", [{ label: "Tentar de novo", color: "neutral" } as never])[0]).toMatchObject({
      color: "error",
      variant: "solid",
    });
    expect(alertActions("error", [false, null, { label: "x" }])).toHaveLength(1);
  });

  it("a trava reconhece o certo e o errado", () => {
    expect(alertActionProblems(`<NuxtAlert color="error" :actions="alertActions('error', a)" />`)).toEqual([]);
    expect(alertActionProblems(`<NuxtAlert :color="tone" :actions="alertActions(tone, a)" />`)).toEqual([]);
    expect(alertActionProblems(`<NuxtAlert color="error" :actions="a" />`)).toHaveLength(1);
    expect(alertActionProblems(`<NuxtAlert color="warning" :actions="alertActions('info', a)" />`)).toHaveLength(1);
    expect(
      alertActionProblems(
        `<NuxtAlert color="info"><template #actions><NuxtButton color="primary" /></template></NuxtAlert>`,
      ),
    ).toHaveLength(1);
    expect(
      alertActionProblems(
        `<NuxtAlert color="info"><template #actions><NuxtButton color="info" /></template></NuxtAlert>`,
      ),
    ).toEqual([]);
  });

  it("o kit e os apps de operador seguem a regra", () => {
    const dirs = ["operator-kit", ...OPERATOR_SURFACES];
    const found: Record<string, string[]> = {};
    for (const dir of dirs) {
      for (const path of vueFiles(join(surfacesDir, dir, "app"))) {
        const problems = alertActionProblems(readFileSync(path, "utf8"));
        if (problems.length) found[relative(surfacesDir, path)] = problems;
      }
    }
    const beyondDebt = Object.fromEntries(
      Object.entries(found).filter(([path, problems]) => problems.length > (KNOWN_APP_DEBT[path] ?? 0)),
    );
    expect(beyondDebt).toEqual({});
    // A dívida só encolhe: o que já está na regra sai da lista.
    const paid = Object.keys(KNOWN_APP_DEBT).filter((path) => (found[path]?.length ?? 0) < KNOWN_APP_DEBT[path]!);
    expect(paid).toEqual([]);
  });
});
