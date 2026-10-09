import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Trava da AÇÃO NA BASE (WP-FASE2-UX-OPERADOR, D8): a ação do momento no celular é o
// `OperatorActionBar`, em fluxo entre o conteúdo e a barra inferior, nunca uma barra
// grudada na base feita à mão (`sticky`/`fixed` + `bottom-*`).
//
// Motivo medido (09/10/2026): oito barras de base feitas à mão (Cozinha, Marketing, PDV
// ×5, Compras), cada uma adivinhando a altura da barra inferior com um número mágico
// (`bottom-16`, `bottom-20`, `bottom-[calc(4rem…)]`) e sem `data-focus-obstruction`: o
// próximo foco parava atrás delas, e a barra cobria o fim da página.
//
// Uso novo reprova; migrar um uso antigo baixa o teto (o número só cai). As peças do
// kit que SÃO a base (barra do polegar dos apps fora do shell, o aviso de atualização)
// ficam listadas com motivo.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const ROOTS = [...OPERATOR_SURFACES, "operator-kit"].map((dir) => join(surfacesDir, dir, "app"));
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);

/** Um texto entre aspas com `sticky`/`fixed` e `bottom-*`: uma barra grudada na base. */
const STUCK_TO_BOTTOM = /(["'`])((?:(?!\1).)*)\1/g;
const PINNED = /(?:^|[\s:])(?:sticky|fixed)(?=\s|$)/;
const BOTTOM = /(?:^|[\s:])bottom-\S+/;

/**
 * Teto por arquivo, com o motivo. `arriving`: a peça ainda está em PR (o teto vale
 * quando ela chegar; enquanto não chega, não acusa teto velho).
 */
const CEILING: Record<string, { max: number; reason: string; arriving?: string }> = {
  "operator-kit/app/components/OperatorThumbAction.vue": {
    max: 1,
    reason: "o polegar da Saída do Gestor (F7, #1564): mesmo papel da ação na base; unifica com o OperatorActionBar",
  },
  "operator-kit/app/components/OperatorSectionBar.vue": {
    max: 1,
    reason: "a barra do polegar dos apps ainda fora do shell (é a barra de base)",
  },
  "operator-kit/app/components/OperatorPwaRuntime.vue": {
    max: 1,
    reason: "o aviso de versão nova do app instalado, acima da barra inferior",
  },
  "kds-nuxt/app/pages/[ref].vue": { max: 1, reason: "dívida: \"Pronto\" da Cozinha, onda da Cozinha" },
  "marketing-nuxt/app/components/AnnouncementCard.vue": { max: 1, reason: "dívida: Revisão, onda do Marketing" },
  "pos-nuxt/app/pages/session/closing.vue": { max: 3, reason: "dívida: Fim do dia, onda do PDV" },
  "pos-nuxt/app/pages/preorders/index.vue": { max: 1, reason: "dívida: Encomendas, onda do PDV" },
  "pos-nuxt/app/pages/index.vue": { max: 2, reason: "dívida: comanda e barra de funções da venda, onda do PDV" },
  "pos-nuxt/app/pages/settings/seating.vue": { max: 1, reason: "dívida: Ajustes do salão, onda do PDV" },
};

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

export function stuckToBottomCount(source: string): number {
  let count = 0;
  for (const [, , text] of template(source).matchAll(STUCK_TO_BOTTOM)) {
    if (text && PINNED.test(text) && BOTTOM.test(text)) count += 1;
  }
  return count;
}

function counts(): Map<string, number> {
  const found = new Map<string, number>();
  for (const root of ROOTS) {
    for (const file of vueFiles(root)) {
      const hits = stuckToBottomCount(readFileSync(file, "utf8"));
      if (hits) found.set(relative(surfacesDir, file), hits);
    }
  }
  return found;
}

describe("ação na base: só pelo OperatorActionBar", () => {
  it("reconhece a barra grudada à mão, e não o resto", () => {
    expect(stuckToBottomCount('<template><div class="sticky bottom-0 bg-card"></div></template>')).toBe(1);
    expect(stuckToBottomCount('<template><div class="fixed inset-x-0 bottom-16"></div></template>')).toBe(1);
    expect(stuckToBottomCount('<template><div class="sticky top-0"></div><p class="mb-2">bottom-line</p></template>')).toBe(0);
  });

  it("nenhuma barra grudada na base fora do teto declarado", () => {
    const offenders = [...counts()]
      .filter(([file, hits]) => hits > (CEILING[file]?.max ?? 0))
      .map(([file, hits]) => `${file}: ${hits}`);
    expect(offenders, "use <OperatorActionBar> (README, \"Ação na base\")").toEqual([]);
  });

  it("o teto acompanha o código (o número só cai)", () => {
    const found = counts();
    const stale = Object.entries(CEILING)
      .filter(([file, { max, arriving }]) => !arriving && (found.get(file) ?? 0) < max)
      .map(([file, { max }]) => `${file}: teto ${max}, hoje ${found.get(file) ?? 0}`);
    expect(stale, "baixe o teto em CEILING").toEqual([]);
  });
});
