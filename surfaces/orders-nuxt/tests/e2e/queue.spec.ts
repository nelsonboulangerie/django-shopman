import { test, expect } from "@playwright/test";

// A Fila "Precisa de você" (V4-G4): o desktop abre nela; só o fato humano é botão, o
// resto vira número e a Supervisão (as três colunas) segue a um toque e na tecla T.
test.use({ viewport: { width: 1440, height: 900 } });

test("o desktop abre na Fila, por urgência, com a coluna de consciência", async ({ page }) => {
  await page.goto("/");
  const queue = page.locator("[data-queue-view]");
  await expect(queue.getByRole("heading", { name: "Precisa de você" })).toBeVisible();
  const items = queue.locator("[data-queue-item]");
  await expect(items).toHaveCount(2);
  // O bloqueado está mais longe da meta (8 de 5 min) e vem primeiro, com o gesto travado.
  await expect(items.first()).toHaveAttribute("data-queue-item", "blocked");
  await expect(items.first().locator("[data-queue-primary]")).toBeDisabled();
  await expect(items.nth(1).getByRole("button", { name: "Iniciar preparo" })).toBeEnabled();
  await expect(items.nth(1).locator("[data-queue-goal]")).toHaveText("meta 5");
  // O resto vira número; o agregado, o que o sistema fez e o cardápio ao lado.
  await expect(queue.locator("[data-queue-rest]")).toContainText("+1");
  await expect(queue.locator("[data-queue-progress]")).toContainText("Na Cozinha");
  await expect(queue.locator("[data-queue-system]")).toContainText("Aceito · prazo de confirmação");
  await expect(queue.locator("[data-queue-menu]")).toContainText("Bichon au Citron esgotado");
  await expect(queue.locator("[data-queue-menu]")).toContainText("iFood recebendo pedidos");
});

test("Ver todos e T abrem a Supervisão; F volta para a Fila", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("[data-queue-view]")).toBeVisible();
  await page.locator("[data-queue-rest]").click();
  await expect(page.locator("[data-board-columns]")).toBeVisible();
  await page.keyboard.press("f");
  await expect(page.locator("[data-queue-view]")).toBeVisible();
  await page.keyboard.press("t");
  await expect(page.locator("[data-board-columns]")).toBeVisible();
  await page.getByRole("button", { name: "Fila: o que precisa de você" }).click();
  await expect(page.locator("[data-queue-view]")).toBeVisible();
});

test("tablet em pé segue com as colunas (a Fila é do desktop)", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/");
  await expect(page.locator("[data-board-columns]")).toBeVisible();
  await expect(page.locator("[data-queue-view]")).toHaveCount(0);
});
