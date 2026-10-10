import { test, expect, type Locator } from "@playwright/test";

// O alvo da suíte é a altura `md` do Nuxt UI, 32 px pelo token `control` (decisão do
// dono de 09/10/2026, operator-kit/README "Alvo de toque de 32 px pelo token").
const TARGET = 32;

for (const touch of [false, true]) {
  test.describe(touch ? "Alvos touch" : "Alvos desktop", () => {
    test.use({ hasTouch: touch, viewport: touch ? { width: 768, height: 1024 } : { width: 1440, height: 1000 } });
    test("busca, seleção, ordenação e troca de visão têm área operacional", async ({ page }, testInfo) => {
      async function target(locator: Locator, label: string) {
        await expect(locator).toBeVisible();
        const box = await locator.boundingBox();
        expect.soft(box?.width, `${label}: largura`).toBeGreaterThanOrEqual(TARGET);
        expect.soft(box?.height, `${label}: altura`).toBeGreaterThanOrEqual(TARGET);
      }
      // O quadro de colunas é a Supervisão (V4-G4: o desktop abre na Fila).
      await page.goto("/?view=board");
      await expect(page.getByText("Ana · Loja online", { exact: true })).toBeVisible();
      // v4 (UX-KIT-V2): atender e a seleção em lote moram no ⋯ do cartão; a caixa volta
      // ao cartão no modo de seleção.
      const cardMenu = page.locator("[data-card-menu]").first();
      await target(cardMenu, "Mais ações do cartão");
      await cardMenu.click();
      // Item de menu é linha de lista do Nuxt UI, não controle: basta estar lá.
      await expect(page.getByRole("menuitem", { name: "Atender este pedido", exact: true }).first()).toBeVisible();
      await page.locator("[data-card-select-mode]").first().click();
      await target(page.getByRole("button", { name: "Desmarcar pedido", exact: true }).first(), "Seleção card");
      await page.locator("[data-bulk-bar] [data-operator-bulk-clear]").filter({ visible: true }).first().click();
      await target(page.locator("[data-sound-toggle]").filter({ visible: true }).first(), "Som");
      await target(page.getByRole("button", { name: "Avisos", exact: true }), "Avisos");
      await target(page.getByRole("button", { name: "Iniciar preparo", exact: true }), "Ação principal");
      // A busca abre a paleta da suíte; "Filtrar o quadro" recorta o quadro desta tela.
      const search = page.getByRole("button", { name: touch ? "Buscar" : "Buscar por código, cliente ou item (atalho: /)", exact: true });
      await target(search, "Busca");
      await search.click();
      await page.getByRole("textbox", { name: "Buscar pedido, cliente ou item" }).fill("Ana");
      await page.getByRole("option", { name: "Filtrar o quadro por “Ana”" }).click();
      await expect(page.getByText("Pagamento pendente · Loja online", { exact: true })).toHaveCount(0);
      await expect(page.getByText("Ana · Loja online", { exact: true })).toBeVisible();
      await page.goto("/?view=board");
      const more = page.getByRole("button", { name: "Mais ações da fila", exact: true });
      await target(more, "Mais ações da fila");
      if (touch) {
        // Tablet em pé: ordenar e a visão entram no ⋯ do quadro (o cabeçalho fica numa linha).
        await more.click();
        await expect(page.getByRole("menuitem", { name: "Urgência", exact: true })).toBeVisible();
        await page.screenshot({ path: testInfo.outputPath("board.png") });
        await page.getByRole("menuitem", { name: "Lista", exact: true }).click();
      } else {
        const sort = page.getByRole("button", { name: "Chegada", exact: true });
        await target(sort, "Ordenar");
        await target(page.getByRole("tab", { name: "Grade", exact: true }), "Modo grade");
        await target(page.getByRole("tab", { name: "Lista", exact: true }), "Modo lista");
        await page.screenshot({ path: testInfo.outputPath("board.png") });
        await page.getByRole("tab", { name: "Lista", exact: true }).click();
      }
      const table = page.getByRole("table", { name: "Lista dos pedidos em andamento" });
      await expect(table).toBeVisible();
      // A caixa da Lista é a do `OperatorTable` do kit (checkbox do Nuxt UI, 16 px): o
      // alvo dela é decisão do kit, não do Gestor. Aqui basta que exista e marque.
      const rowBox = table.getByRole("checkbox", { name: "Selecionar o pedido WEB-20260625-0007" });
      await rowBox.click();
      await expect(rowBox).toBeChecked();
      await page.screenshot({ path: testInfo.outputPath("table.png") });
    });
  });
}
