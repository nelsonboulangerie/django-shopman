import { test, expect } from "@playwright/test";

test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

test("agendamento e entrega iFood ficam legíveis no celular", async ({ page }, testInfo) => {
  await page.goto("/");
  // No celular, com o som bloqueado pelo navegador, o quadro abre pedindo o toque que o
  // libera ("Toque para começar"); se o navegador já deixa tocar, a janela não aparece.
  // A busca mora na lupa da linha do chão e abre a paleta da suíte; a primeira opção é
  // "Filtrar o quadro" ("Nesta tela").
  const start = page.getByRole("button", { name: "Começar", exact: true });
  await start
    .waitFor({ state: "visible", timeout: 3_000 })
    .then(() => start.click())
    .catch(() => {});
  await page.getByRole("button", { name: "Buscar por código, cliente ou item", exact: true }).click();
  await page.getByRole("textbox", { name: "Buscar pedido, cliente ou item" }).fill("IFOOD-260914-1515");
  await page.getByRole("option", { name: "Filtrar o quadro por “IFOOD-260914-1515”" }).click();
  // O quadro filtrado mostra só o pedido agendado, com o avanço travado e o motivo.
  const card = page.locator("article").filter({ hasText: "Pedido iFood agendado" });
  await expect(card).toBeVisible();
  await expect(page.locator("article").filter({ hasText: "Ana · " })).toHaveCount(0);
  // O resumo do iFood (entrega, preparo, janela) mora no detalhe do pedido.
  await card.getByRole("link", { name: "Abrir pedido IFOOD-260914-1515" }).click();
  await expect(page).toHaveURL(/\/IFOOD-260914-1515$/);
  await expect(page.getByText("Entrega por entregador iFood", { exact: true })).toBeVisible();
  await expect(page.getByText("Início do preparo: 14/09/2026 às 15:15", { exact: true })).toBeVisible();
  await expect(page.getByText("Fim da janela: 14/09/2026 às 16:30", { exact: true })).toBeVisible();
  await expect(page.locator("[data-detail-block]")).toContainText("O horário de preparo do iFood ainda não permite avançar.");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("ifood-mobile.png"), fullPage: true });
});
