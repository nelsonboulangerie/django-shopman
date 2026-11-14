import { test, expect } from "@playwright/test";

// A Fila "Precisa de você" (V4-G4): a um toque do Quadro (a casa, dono 14/11/2026) e na
// tecla G; só o fato humano é botão, o resto vira número e a Tabela segue na tecla L.
test.use({ viewport: { width: 1440, height: 900 } });

test("o desktop abre no Quadro; a Fila vem por urgência, com a coluna de consciência", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("[data-board-columns]")).toBeVisible();
  await expect(page.locator("[data-queue-view]")).toHaveCount(0);
  await page.keyboard.press("g");
  const queue = page.locator("[data-queue-view]");
  await expect(queue.getByRole("heading", { name: "Precisa de você" })).toBeVisible();
  const items = queue.locator("[data-queue-item]");
  await expect(items).toHaveCount(2);
  // O bloqueado está mais longe da meta (8 de 5 min) e vem primeiro, com o gesto travado.
  await expect(items.first()).toHaveAttribute("data-queue-item", "blocked");
  await expect(items.first().locator("[data-queue-primary]")).toBeDisabled();
  await expect(items.nth(1).getByRole("button", { name: "Iniciar preparo" })).toBeEnabled();
  await expect(items.nth(1).locator("[data-queue-goal]")).toHaveText("meta 5");
  // O resto vira contagem com nome (sem "+N" somando grandezas); o agregado, o que o
  // sistema fez e o cardápio ao lado.
  // Só o que está em preparo conta: o iFood agendado, aceito e esperando o horário,
  // não foi para a cozinha (beta 05/11, GES-13).
  await expect(queue.locator("[data-queue-rest]")).toContainText("Seguem sozinhos: 1 na cozinha");
  await expect(queue.locator("[data-queue-rest]")).not.toContainText("+");
  await expect(queue.locator("[data-queue-progress]")).toContainText("Na Cozinha");
  await expect(queue.locator("[data-queue-system]")).toContainText("Aceito · prazo de confirmação");
  await expect(queue.locator("[data-queue-menu]")).toContainText("Bichon au Citron esgotado");
  await expect(queue.locator("[data-queue-menu]")).toContainText("iFood");
});

test("L abre a Tabela e G volta para a Fila", async ({ page }) => {
  await page.goto("/?view=queue");
  await expect(page.locator("[data-queue-view]")).toBeVisible();
  await page.keyboard.press("l");
  await expect(page.locator("[data-supervision-table]")).toBeVisible();
  await page.keyboard.press("g");
  await expect(page.locator("[data-queue-view]")).toBeVisible();
  await page.getByRole("tab", { name: "Tabela" }).click();
  await expect(page.locator("[data-supervision-table]")).toBeVisible();
});

test("tablet em pé segue com o quadro em abas (a Fila é do desktop)", async ({ page }) => {
  // Três colunas de ~240 px cortavam selo e prazo do cartão: abaixo do lg o quadro usa
  // as abas do celular, uma etapa por vez (74932fb8f, 07/10/2026).
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "Em preparo 4" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("Ana · Loja online", { exact: true })).toBeVisible();
  await expect(page.locator("[data-board-columns]")).toHaveCount(0);
  await expect(page.locator("[data-queue-view]")).toHaveCount(0);
});
