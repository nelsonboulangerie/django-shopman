import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrail de PROPRIEDADE: o que o kit já possui não volta a nascer copiado no app.
//
// Motivo medido: `apiPath` existia em SETE cópias com TRÊS nomes (`apiPath`,
// `hubApiPath`, `posApiPath`), `operatorSessionOnError` em SEIS, a casca do BFF
// `/api/v1/**` nos OITO, e as quatro primitivas de barra em duas — e a cópia mais
// nova tinha trocado o token de alvo de toque por literal, derrubando o chip para
// 36 px. Cópia byte a byte não dói no dia em que é feita; dói no dia em que UMA
// delas muda. Este arquivo é o teste de varredura que cobra o gêmeo que falta:
// quem precisar da peça importa do kit, e quem precisar de comportamento DIFERENTE
// dá um nome próprio (é o que o Marketing faz com `marketingSessionOnError`).
//
// Storefront fica FORA: não estende esta layer (superfície de cliente, proxy, CSRF
// e harness próprios).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const OPERATOR_APPS = [
  "bi-nuxt",
  "hub-nuxt",
  "kds-nuxt",
  "marketing-nuxt",
  "orders-nuxt",
  "pos-nuxt",
  "production-nuxt",
  "purchase-nuxt",
] as const;

/** Declarações que pertencem ao kit e não podem reaparecer no app — inclusive com
 * outro nome, que foi exatamente como as sete cópias de `apiPath` se esconderam.
 * O gatilho é o `export` (a peça sendo REDECLARADA), não o `const apiPath = ...`
 * com que cada chamador amarra o retorno de `useApiPath()`. */
const KIT_OWNED_DECLARATIONS = [
  /\bexport\s+(?:function|const)\s+\w*[aA]piPath\b/,
  /\bexport\s+(?:function|const)\s+operatorSessionOnError\b/,
] as const;

/** Componentes de barra que agora vivem no kit (nome global `Ui<Nome>`). */
const KIT_OWNED_TOOLBAR_PRIMITIVES = ["FilterChip", "IconButton", "SearchInput", "Toolbar"] as const;

function sourceFiles(dir: string, found: string[] = []): string[] {
  if (!existsSync(dir)) return found;
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".nuxt" || entry === ".output") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (full.endsWith(".ts") || full.endsWith(".vue")) found.push(full);
  }
  return found;
}

describe("operator-kit: o que é do kit não renasce copiado no app", () => {
  for (const app of OPERATOR_APPS) {
    it(`${app} não redeclara apiPath nem operatorSessionOnError`, () => {
      const offenders: string[] = [];
      for (const file of sourceFiles(resolve(surfacesDir, app, "app"))) {
        const source = readFileSync(file, "utf8");
        for (const pattern of KIT_OWNED_DECLARATIONS) {
          if (pattern.test(source)) {
            offenders.push(`${file.slice(surfacesDir.length + 1)} → ${pattern.source}`);
          }
        }
      }
      expect(
        offenders,
        `Peça do kit redeclarada no app (importe do operator-kit; se o comportamento ` +
          `for DIFERENTE, dê um nome próprio como o marketingSessionOnError):\n  ` +
          offenders.join("\n  "),
      ).toEqual([]);
    });

    it(`${app} não tem cópia própria das primitivas de barra`, () => {
      const offenders = KIT_OWNED_TOOLBAR_PRIMITIVES.filter((name) =>
        existsSync(resolve(surfacesDir, app, "app/components/Ui", `${name}.vue`)),
      );
      expect(
        offenders,
        `Primitiva de barra copiada no app: ${offenders.join(", ")}. ` +
          `A canônica é <Ui${offenders[0] ?? "…"}> do operator-kit.`,
      ).toEqual([]);
    });

    it(`${app} usa a rota /api/v1/** do kit, sem casca própria`, () => {
      expect(
        existsSync(resolve(surfacesDir, app, "server/api/v1/[...path].ts")),
        `${app} recriou a casca do BFF; o handler único vive em ` +
          `operator-kit/server/api/v1/[...path].ts e chega por extends.`,
      ).toBe(false);
    });
  }

  it("o kit é quem serve /api/v1/** das oito superfícies", () => {
    expect(existsSync(resolve(surfacesDir, "operator-kit/server/api/v1/[...path].ts"))).toBe(true);
  });
});

describe("operator-kit: primitivas de barra respeitam o token de alvo de toque", () => {
  // `--spacing-control: 2.75rem` (44 px) vive no operator-theme.css. O literal
  // equivalente (`size-11`/`h-11`) renderiza igual HOJE e some no dia em que o token
  // mudar; foi assim que a cópia do Marketing acabou com um chip de `h-9` (36 px).
  const TOKENLESS = /\b(?:size|h|min-h)-(?:9|10|11)\b/;

  // Comentário fora ANTES de medir: o próprio cabeçalho destes arquivos CITA o `h-9`
  // que a cópia tinha, e citar a dívida não é cometê-la.
  const stripComments = (text: string): string =>
    text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "").replace(/<!--[\s\S]*?-->/g, "");

  for (const name of KIT_OWNED_TOOLBAR_PRIMITIVES) {
    it(`Ui${name} usa *-control, nunca altura literal`, () => {
      const source = readFileSync(resolve(surfacesDir, "operator-kit/app/components", `Ui${name}.vue`), "utf8");
      expect(TOKENLESS.test(stripComments(source)), `Ui${name} voltou a cravar altura literal em vez do token`).toBe(false);
    });
  }

  it("o alvo de toque canônico continua em 44 px no tema central", () => {
    const theme = readFileSync(resolve(surfacesDir, "operator-kit/app/assets/css/operator-theme.css"), "utf8");
    expect(theme).toMatch(/--spacing-control:\s*2\.75rem;/);
  });
});
