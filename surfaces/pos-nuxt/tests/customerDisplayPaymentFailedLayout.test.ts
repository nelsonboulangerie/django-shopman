import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A fase `payment_failed` da tela do cliente segue a coluna do RESULTADO: sem
// largura máxima (o título cabia em uma linha em 1920 e quebrava em duas por uma
// coluna de 56rem), e o ícone de alerta centrado ACIMA do título, num bloco só
// (antes ficava solto à esquerda, longe do título). Defeito medido na prévia do #2537.
const here = dirname(fileURLToPath(import.meta.url));
const DISPLAY = readFileSync(resolve(here, "..", "app", "pages", "display.vue"), "utf8");

function section(phase: string): string {
  const start = DISPLAY.indexOf(`phase === '${phase}'`);
  expect(start, `fase ${phase} existe`).toBeGreaterThan(-1);
  const end = DISPLAY.indexOf("</section>", start);
  return DISPLAY.slice(start, end);
}

describe("tela do cliente: cobrança não concluída", () => {
  const failed = section("payment_failed");

  it("não aperta o título numa coluna estreita", () => {
    expect(failed).not.toMatch(/max-w-/);
    expect(failed).toContain("text-balance");
  });

  it("o ícone fica acima do título, no mesmo bloco centrado", () => {
    const block = failed.match(/<div class="grid justify-items-center[^"]*"[^>]*>([\s\S]*?)<\/div>/);
    expect(block, "bloco do título").not.toBeNull();
    const inner = block![1]!;
    const icon = inner.indexOf('name="lucide:circle-alert"');
    const title = inner.indexOf("Pagamento não concluído");
    expect(icon).toBeGreaterThan(-1);
    expect(title).toBeGreaterThan(icon);
    // O título não divide a linha com o ícone (o par lado a lado é o que deslocava).
    expect(failed).not.toMatch(/<p class="flex items-center[^"]*">\s*<Icon name="lucide:circle-alert"/);
  });

  it("o título tem a mesma escala do obrigado", () => {
    expect(failed).toContain("text-5xl font-semibold tracking-tight md:text-7xl");
  });
});
