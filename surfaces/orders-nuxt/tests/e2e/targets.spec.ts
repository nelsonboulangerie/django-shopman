import { test, expect, type Locator } from "@playwright/test";

for (const touch of [false, true]) {
  test.describe(touch ? "Alvos touch" : "Alvos desktop", () => {
    test.use({ hasTouch: touch, viewport: touch ? { width: 768, height: 1024 } : { width: 1440, height: 1000 } });
    test("busca, seleção, ordenação e troca de visão têm área operacional", async ({ page }, testInfo) => {
      async function target(locator: Locator, label: string) {
        await expect(locator).toBeVisible();
        const box = await locator.boundingBox();
        expect.soft(box?.width, `${label}: largura`).toBeGreaterThanOrEqual(44);
        expect.soft(box?.height, `${label}: altura`).toBeGreaterThanOrEqual(44);
      }
      // O quadro de colunas é a Supervisão (V4-G4: o desktop abre na Fila).
      await page.goto("/?view=board");
      await expect(page.getByText("Ana", { exact: true })).toBeVisible();
      // v4 (UX-KIT-V2): atender e a seleção em lote moram no ⋯ do cartão; a caixa volta
      // ao cartão no modo de seleção.
      const cardMenu = page.locator("[data-card-menu]").first();
      await target(cardMenu, "Mais ações do cartão");
      await cardMenu.click();
      await target(page.getByRole("menuitem", { name: "Atender este pedido", exact: true }).first(), "Atribuição");
      await page.locator("[data-card-select-mode]").first().click();
      await target(page.getByRole("button", { name: "Desmarcar pedido", exact: true }).first(), "Seleção card");
      await page.locator("[data-bulk-bar] [data-operator-bulk-clear]").filter({ visible: true }).first().click();
      await target(page.locator("[data-sound-toggle]"), "Som");
      await target(page.getByTitle("Alertas", { exact: true }), "Alertas");
      await target(page.getByRole("button", { name: "Avisos", exact: true }), "Avisos");
      const primary = page.getByRole("button", { name: "Iniciar preparo", exact: true });
      const primaryBox = await primary.boundingBox();
      expect.soft(primaryBox?.height, "Ação principal: altura").toBeGreaterThanOrEqual(48);
      const search = page.getByRole("searchbox");
      await target(search, "Busca");
      await search.fill("Ana");
      await target(page.getByRole("button", { name: "Limpar busca" }), "Limpar busca");
      await page.getByRole("button", { name: "Limpar busca" }).click();
      if (touch) {
        // Tablet em pé: ordenar e a visão entram no ⋯ do quadro (o cabeçalho fica numa linha).
        const more = page.locator("[data-board-more]");
        await target(more, "Mais ações da fila");
        await more.click();
        await target(page.getByRole("menuitemradio").first(), "Opção de ordenação");
        await target(page.getByRole("menuitemradio", { name: "Tabela" }), "Modo tabela");
        await page.screenshot({ path: testInfo.outputPath("board.png") });
        await page.getByRole("menuitemradio", { name: "Tabela" }).click();
      } else {
        const sort = page.getByTitle("Ordenar (atalho: s)");
        await target(sort, "Ordenar");
        await sort.click();
        await target(page.getByRole("menuitemradio").first(), "Opção de ordenação");
        await page.getByRole("menuitemradio").first().click();
        await target(page.getByRole("button", { name: "Ver em tabela" }), "Modo tabela");
        await target(page.getByRole("button", { name: "Supervisão: ver em colunas" }), "Modo colunas");
        await target(page.getByRole("button", { name: "Fila: o que precisa de você" }), "Modo fila");
        await page.screenshot({ path: testInfo.outputPath("board.png") });
        await page.getByRole("button", { name: "Ver em tabela" }).click();
      }
      await target(page.getByRole("button", { name: "Selecionar todos", exact: true }), "Selecionar todos");
      await target(page.getByRole("button", { name: "Selecionar pedido", exact: true }).first(), "Seleção tabela");
      await page.screenshot({ path: testInfo.outputPath("table.png") });
    });
  });
}
