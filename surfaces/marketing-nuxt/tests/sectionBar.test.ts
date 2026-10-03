import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function read(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

// Regressão de 03/10/2026 (a11y.spec.ts, 320×568): a barra do polegar era
// `fixed inset-x-0`, cobria o rail inteiro, e o botão "Tema escuro" no pé do rail
// recebia o toque na pílula da barra. A barra mora no fim da COLUNA de conteúdo.
describe("barra do polegar do Marketing", () => {
  const bar = read("../app/components/MarketingSectionBar.vue");
  const shell = read("../app/app.vue");

  it("não é fixa na largura da janela", () => {
    const template = bar.slice(bar.indexOf("<template>"));
    expect(template).not.toMatch(/\bfixed\b/);
    expect(template).not.toContain("inset-x-0");
    expect(template).toContain("sticky bottom-0");
  });

  it("mora no fim da coluna de conteúdo, depois da página, fora do rail", () => {
    const column = shell.indexOf("<CampaignTopBar />");
    const page = shell.indexOf('<component :is="Component" />');
    const barAt = shell.indexOf("<MarketingSectionBar />");
    expect(column).toBeGreaterThan(shell.indexOf("<OperatorRail"));
    expect(page).toBeGreaterThan(column);
    expect(barAt).toBeGreaterThan(page);
  });

  it("se declara obstáculo da base para o próximo foco e o 'Tem mais abaixo'", () => {
    expect(bar).toContain("data-focus-obstruction");
  });
});
