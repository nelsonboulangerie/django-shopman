import { test, expect } from "@playwright/test";

test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

test("agendamento e entrega iFood ficam legíveis no celular", async ({ page }, testInfo) => {
  await page.goto("/");
  // No celular a busca mora atrás da lupa da barra de 56px e abre a paleta da suíte;
  // Enter escolhe "Filtrar o quadro" (a primeira opção, "Nesta tela").
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await page.getByRole("textbox", { name: "Buscar pedido, cliente ou item" }).fill("IFOOD-SCHEDULED");
  await page.getByRole("option", { name: "Filtrar o quadro por “IFOOD-SCHEDULED”" }).click();
  // O quadro filtrado mostra só o pedido agendado, com o avanço travado e o motivo.
  const card = page.locator("article").filter({ hasText: "Pedido iFood agendado" });
  await expect(card).toBeVisible();
  await expect(page.locator("article").filter({ hasText: "Ana · " })).toHaveCount(0);
  // O resumo do iFood (entrega, preparo, janela) mora no detalhe do pedido.
  await card.getByRole("link", { name: "Abrir pedido IFOOD-SCHEDULED" }).click();
  await expect(page).toHaveURL(/\/IFOOD-SCHEDULED$/);
  await expect(page.getByText("Entrega por entregador iFood", { exact: true })).toBeVisible();
  await expect(page.getByText("Início do preparo: 14/09/2026 às 15:15", { exact: true })).toBeVisible();
  await expect(page.getByText("Fim da janela: 14/09/2026 às 16:30", { exact: true })).toBeVisible();
  await expect(page.locator("[data-detail-block]")).toContainText("O horário de preparo do iFood ainda não permite avançar.");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("ifood-mobile.png"), fullPage: true });
});
