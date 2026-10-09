import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { belowQuery } from "../app/presentation/screen";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// A régua de tela é UMA, a do kit (`useScreen`), e segura para o SSR.
//
// O que voltava sem isto (Gestor, 09/10/2026, no alpha): dez telas declaravam a própria
// régua com `useMediaQuery` (639 px em nove, 1279 px na fila com o mesmo nome `isNarrow`)
// e decidiam `v-if` de layout com ela. O servidor não sabe a largura e desenhava a mesa;
// na carga direta no celular o cliente hidratava outra árvore. A Fila ficava no
// esqueleto para sempre (`Cannot read properties of null (reading 'emitsOptions')`) e a
// toolbar do Histórico, dos Clientes e do Catálogo sumia. Navegando por dentro, certo.
//
// Regra: `useMediaQuery` só mora no kit, na régua (`useScreen`) e no rail
// (`useSuiteRailShown`, que é orientação além de largura). Nos apps, a tela lê
// `useScreen()` para decidir árvore e escreve `max-sm:`/`md:` no CSS para o que é só
// apresentação. Os apps ainda não migrados têm teto: o número só cai. Prova no
// navegador: `orders-nuxt/tests/ssr/directLoadPhone.spec.ts` (build de produção, 390 px).
//
// ⚠️ Lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");

const KIT_ALLOWED = new Set(["app/composables/useScreen.ts", "app/composables/useSuiteChrome.ts"]);

/** Teto por app ainda não migrado (09/10/2026). Migrou? Baixe o número; nunca suba. */
const CEILING: Record<string, number> = {
  "bi-nuxt": 7,
  "kds-nuxt": 1,
  "marketing-nuxt": 1,
  "pos-nuxt": 7,
  "production-nuxt": 3,
  "purchase-nuxt": 3,
};

function sourceFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" || entry.name.startsWith(".") ? [] : sourceFiles(path);
    return /\.(vue|ts)$/.test(entry.name) ? [path] : [];
  });
}

/** As chamadas a `useMediaQuery(` fora de comentário, por arquivo. */
function mediaQueryCalls(appDir: string): Map<string, number> {
  const calls = new Map<string, number>();
  for (const file of sourceFiles(join(appDir, "app"))) {
    const code = readFileSync(file, "utf8")
      .split("\n")
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
      .join("\n");
    const count = (code.match(/\buseMediaQuery\(/g) ?? []).length;
    if (count) calls.set(relative(appDir, file), count);
  }
  return calls;
}

describe("régua de tela única (useScreen)", () => {
  it("as bordas são as do Tailwind (a mesma do `max-sm:` do CSS)", () => {
    expect(belowQuery("sm")).toBe("(max-width: 639.98px)");
    expect(belowQuery("md")).toBe("(max-width: 767.98px)");
    expect(belowQuery("lg")).toBe("(max-width: 1023.98px)");
    expect(belowQuery("xl")).toBe("(max-width: 1279.98px)");
  });

  it("no kit, `useMediaQuery` só na régua e no rail; `ssrWidth` em lugar nenhum", () => {
    const outside = [...mediaQueryCalls(kitDir).keys()].filter((file) => !KIT_ALLOWED.has(file));
    expect(outside, "use `useScreen()` (composables/useScreen.ts)").toEqual([]);
    const ssrWidth = sourceFiles(join(kitDir, "app")).filter((file) => /\bssrWidth\b/.test(readFileSync(file, "utf8")));
    expect(ssrWidth.map((file) => relative(kitDir, file)), "`ssrWidth` adivinha a largura no servidor; use `useScreen()`").toEqual([]);
  });

  it("nos apps de operador, nenhuma régua própria além do teto (o Gestor já é zero)", () => {
    const over: string[] = [];
    for (const app of OPERATOR_SURFACES) {
      if (app === "operator-kit") continue;
      const calls = mediaQueryCalls(join(surfacesDir, app));
      const total = [...calls.values()].reduce((sum, n) => sum + n, 0);
      const ceiling = CEILING[app] ?? 0;
      if (total > ceiling) over.push(`${app}: ${total} > ${ceiling} (${[...calls.keys()].join(", ")})`);
    }
    expect(over, "decida a árvore com `useScreen()` do kit e o resto com `max-sm:`/`md:` no CSS").toEqual([]);
  });
});
