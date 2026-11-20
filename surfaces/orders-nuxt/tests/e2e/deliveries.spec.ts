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
    await expect(page.getByRole("button", { name: "Pedido A47, parada 1 da corrida C", exact: true })).toBeVisible();
    await expect(page.getByText(/[Cc]orrida \d/)).toHaveCount(0);
  });

  test("a corrida em edição cota em duas linhas, segue a ordem da rota e deixa conferir o troco", async ({ page }) => {
    await page.goto("/delivery");
    // Toca primeiro o mais longe: a ordem mostrada é a da rota, nunca a dos toques.
    await page.getByRole("button", { name: /C03 · Caio/ }).click();
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    const quote = page.locator("[data-ride-quote]");
    await expect(quote.getByText("Juntas: R$ 16,50 · 24 min · 5,7 km ✔", { exact: true })).toBeVisible();
    await expect(quote.getByText("Separadas sairiam R$ 25,00", { exact: true })).toBeVisible();
    await expect(page.getByText("O entregador sai da loja e segue esta ordem.", { exact: true })).toBeVisible();
    // Por extenso: "2 de 4" obrigava o leitor a adivinhar de 4 o quê.
    await expect(page.locator("[data-ride-capacity]")).toHaveText("2 pedidos (cabem até 4)");
    const order = await page.locator("[data-ride-change]").evaluateAll(() =>
      [...document.querySelectorAll("ol li span.block.op-body")].map((node) => node.textContent?.trim() ?? ""),
    );
    expect(order.slice(0, 2)).toEqual(["A47 · Ana", "C03 · Caio"]);
    // O mapa numera igual à lista: o "1" é o primeiro da rota, não o primeiro toque.
    await expect(page.getByRole("button", { name: "Pedido A47, parada 1 da corrida C", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Pedido C03, parada 2 da corrida C", exact: true })).toBeVisible();
    const change = page.getByRole("textbox", { name: "Troco para C03", exact: true });
    await expect(change).toHaveValue("20,00");
    await change.fill("30,00");
    await expect(change).toHaveValue("30,00");
    await expect(page.getByText("2 pedidos em 1 corrida · R$ 16,50", { exact: false }).first()).toBeVisible();
  });

  test("o detalhe abre pela chave na URL e se apresenta pela letra", async ({ page }) => {
    await page.goto("/delivery?ride=776753358");
    const detail = page.locator("[data-ride-detail]");
    await expect(detail.getByText("Corrida B · Em rota", { exact: true })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Corrida B" })).toBeVisible();
    await expect(detail.getByText(/[Cc]orrida \d/)).toHaveCount(0);
  });
});
