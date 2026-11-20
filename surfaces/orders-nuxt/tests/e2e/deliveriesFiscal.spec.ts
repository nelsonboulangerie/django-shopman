import { expect, test } from "@playwright/test";

// F10 da revisão das Entregas/TaOn, na tela de verdade, contra o mock (cookie
// `e2e_f10` em `mockBackend.mjs`):
//  - a NFC-e não autorizada e a DANFE por imprimir aparecem no topo da página Entregas,
//    como aviso de tela (cor, X, "Abrir o pedido"), e a corrida segue;
//  - o selo de Entregas conta; se a contagem falha, mostra "?", nunca zero.
test.describe("Entregas: a nota fiscal e o selo", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test("NFC-e não autorizada e DANFE por imprimir avisam no topo, e a corrida segue", async ({ context, page, baseURL }) => {
    await context.addCookies([{ name: "e2e_f10", value: "fiscal", url: baseURL! }]);
    await page.goto("/delivery");
    const alerts = page.locator("[data-page-header-alerts]");
    // Corridas na ordem delas: a DANFE de Bia (corrida A) primeiro; a NFC-e de Flora
    // (corrida B) em "e mais 1 aviso".
    await expect(alerts).toContainText("DANFE não impressa no pedido B12");
    await expect(alerts).toContainText("Está na corrida A. A impressora de Balcão recusou a DANFE.");
    await alerts.locator("[data-page-header-alerts-more]").click();
    await expect(alerts).toContainText("NFC-e não autorizada no pedido F09");
    await expect(alerts).toContainText("Está na corrida B, que segue normalmente. O Reprocessar NFC-e fica no pedido.");
    await expect(alerts.getByRole("link", { name: "Abrir o pedido" }).first()).toHaveAttribute("href", "/WEB-20261116-0B12");
    // Só avisa: as corridas continuam lá, com as mesmas letras.
    await expect(page.locator("[data-ride-mirror]")).toHaveCount(2);
    await expect(page.getByText(/—/)).toHaveCount(0);
  });

  test("sem nada fiscal a fazer, nenhum aviso", async ({ page }) => {
    await page.goto("/delivery");
    await expect(page.locator("[data-ride-mirror]")).toHaveCount(2);
    await expect(page.locator("[data-page-header-alerts]")).toHaveCount(0);
  });

  test("o selo conta o que aguarda, e a contagem que falhou é ?", async ({ context, page, baseURL }) => {
    await page.goto("/delivery");
    const section = page.locator("[data-section=deliveries]").first();
    await expect(section).toHaveAttribute("aria-label", "Entregas · 3 pendências");

    await context.addCookies([{ name: "e2e_f10", value: "countfail", url: baseURL! }]);
    await page.reload();
    await expect(section).toHaveAttribute("aria-label", "Entregas · contagem indisponível");
    await expect(section.locator("[data-count-chip]")).toHaveText("?");
  });
});
