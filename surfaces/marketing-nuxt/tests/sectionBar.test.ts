import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function read(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

// Camada visual da suíte (V4-MKT): as seções do Marketing moram no rail da suíte
// (tablet e desktop) e na barra do polegar (celular), as duas peças da layer, e o
// shell as monta pelo `MarketingNav`.
//
// Regressão de 03/10/2026 (a11y.spec.ts, 320×568): a barra do polegar era
// `fixed inset-x-0`, cobria o rail inteiro, e o botão "Tema escuro" no pé do rail
// recebia o toque na pílula da barra. A barra mora no fim da COLUNA de conteúdo.
describe("navegação do Marketing", () => {
  const nav = read("../app/components/MarketingNav.vue");
  const shell = read("../app/app.vue");

  it("veste a camada visual da suíte", () => {
    expect(shell).toContain('data-suite="v3"');
    expect(nav).toContain("<OperatorSuiteRail");
    expect(nav).toContain("<OperatorSectionBar");
    expect(shell).not.toContain("<OperatorRail");
  });

  it("a barra do polegar mora no fim da coluna de conteúdo, depois da página, fora do rail", () => {
    const rail = shell.indexOf('<MarketingNav\n          place="rail"');
    const column = shell.indexOf('<div class="flex min-w-0 flex-1 flex-col">');
    const page = shell.indexOf('<component :is="Component" />');
    const barAt = shell.indexOf('<MarketingNav place="bar" />');
    expect(rail).toBeGreaterThan(-1);
    expect(column).toBeGreaterThan(rail);
    expect(page).toBeGreaterThan(column);
    expect(barAt).toBeGreaterThan(page);
  });

  it("a caixa pessoal tem um dono só, no shell, em qualquer largura", () => {
    expect(shell.match(/<MarketingInboxLive \/>/g)).toHaveLength(1);
    expect(read("../app/components/MarketingNotificationsBell.vue")).not.toContain(
      "useMarketingNotificationInbox",
    );
  });
});
