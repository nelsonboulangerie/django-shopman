import { expect, test } from "@playwright/test";

// A seção Entregas contra o mock: duas corridas na rua (números 1 e 2) e três entregas
// aguardando. Decisão do dono (16/11/2026): corrida se nomeia por LETRA em toda tela;
// o número só escolhe a cor, e a URL do detalhe leva a chave da corrida (`?ride=<chave>`).
test.describe("Entregas: corrida por letra", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test("as corridas vivas aparecem como A e B, nunca como 1 e 2", async ({ page }) => {
    await page.goto("/delivery");
    const mirrors = page.locator("[data-ride-mirror]");
    await expect(mirrors).toHaveCount(2);
    await expect(mirrors.nth(0).locator("span").first()).toHaveText("A");
    await expect(mirrors.nth(1).locator("span").first()).toHaveText("B");
    // No mapa, a moto leva a letra e o nome acessível fala a letra.
    await expect(page.getByRole("button", { name: "Entregador da corrida A", exact: true })).toHaveText("A");
    await expect(page.getByRole("button", { name: "Entregador da corrida B", exact: true })).toHaveText("B");
    await expect(page.getByRole("button", { name: "Corrida B, parada 2, pedido F09", exact: true })).toBeVisible();
    await expect(page.getByText(/[Cc]orrida \d/)).toHaveCount(0);
    await expect(page.locator("[aria-label*='orrida 1'], [aria-label*='orrida 2']")).toHaveCount(0);
  });

  test("a corrida em edição ganha a próxima letra livre, do título ao botão de chamar", async ({ page }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    await expect(page.getByText("Corrida C", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Desfazer a corrida C", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Chamar a corrida C", exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Pedido A47, corrida C", exact: true })).toBeVisible();
    await expect(page.getByText(/[Cc]orrida \d/)).toHaveCount(0);
  });

  test("o detalhe abre pela chave na URL e se apresenta pela letra", async ({ page }) => {
    await page.goto("/delivery?ride=776753358");
    const detail = page.locator("[data-ride-detail]");
    await expect(detail.getByText("Corrida B · Em rota", { exact: true })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Corrida B" })).toBeVisible();
    await expect(detail.getByText(/[Cc]orrida \d/)).toHaveCount(0);
  });
});
