// Trava do indicador do lote no B.I. (UX-PROD-AF2, decisão do dono, 03/10/2026).
//
// O indicador de lote é o APROVEITAMENTO = realizado ÷ previsto (`yield_rate`
// do Craftsman), e a perda é previsto − realizado. "Rendimento" é palavra
// reservada à ficha técnica e à massa, e o B.I. não mostra nem uma nem outra:
// a palavra não volta ao app, nem em comentário, porque quem lê o código
// aprende a palavra errada e a devolve à tela.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const SKIP_DIRS = new Set(["generated", "node_modules", ".nuxt", ".output"]);

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return SKIP_DIRS.has(entry.name) ? [] : walk(full);
    return /\.(vue|ts)$/.test(entry.name) ? [full] : [];
  });
}

const FILES = ["app", "server"].flatMap((dir) => {
  try {
    return walk(join(ROOT, dir));
  } catch {
    return [];
  }
});

describe("indicador do lote no B.I.: aproveitamento, nunca rendimento", () => {
  it("a varredura enxerga a página de Produção", () => {
    const seen = FILES.map((file) => relative(ROOT, file));
    expect(seen).toContain(join("app", "pages", "index.vue"));
  });

  it("nenhum fonte diz rendimento (a palavra é aproveitamento)", () => {
    const hits = FILES.flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .map((line, index) => ({ line, index }))
        .filter(({ line }) => /rendimento/i.test(line))
        .map(({ index }) => `${relative(ROOT, file)}:${index + 1}`),
    );
    expect(hits).toEqual([]);
  });

  it("o aproveitamento do período divide pelo previsto, não pelo planejado", () => {
    const page = readFileSync(join(ROOT, "app", "pages", "index.vue"), "utf8");
    expect(page).toContain("Aproveitamento do período");
    expect(page).not.toMatch(/\/\s*planned\b/);
  });
});
