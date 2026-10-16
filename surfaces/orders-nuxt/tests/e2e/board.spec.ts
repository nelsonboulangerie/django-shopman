import { test, expect } from "@playwright/test";

// Board autenticado (mock devolve sessão + fila): o Gestor passa dos gates e renderiza
// o card do pedido com cliente, itens e total.
test.describe("Gestor — board de pedidos", () => {
  test("sessão autenticada + fila → renderiza o card", async ({ page }) => {
    await page.goto("/?view=board");
    // O mock autoriza o operador (`authorized: true`): sem isso o app abre na recusa
    // "Seu acesso não inclui o Gestor de pedidos" e nenhum teste daqui prova o Gestor.
    await expect(page.getByText("Seu acesso não inclui o Gestor de pedidos")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Pedidos", level: 1 })).toBeVisible();
    await expect(page.getByText("2× Pão · 1× Café")).toBeVisible();
    await expect(page.getByText("R$ 15,00")).toBeVisible();
    await expect(page.getByText("Ana · Loja online", { exact: true })).toBeVisible();
  });

  test("indicador de tempo-real: sem SSE (origem do mock) → 'Atualiza sozinho a cada 30 s'", async ({ page }) => {
    await page.goto("/?view=board");
    // O mock é outra origem (:8796 ≠ :3004) → SSE não conecta → sinal honesto de poll.
    await expect(page.getByText("Atualiza sozinho a cada 30 s")).toBeVisible();
    await expect(page.getByText("Ao vivo")).toHaveCount(0);
  });
});


test("card e lista mantêm o avanço bloqueado e explicam o motivo", async ({ page }) => {
  await page.goto("/?view=board");
  // No cartão o bloqueio é a pílula "Por que espera"; o motivo abre a um toque.
  const card = page.locator("article").filter({ hasText: "Pagamento pendente" });
  await card.getByRole("button", { name: "Por que espera", exact: true }).click();
  await expect(page.getByText("O pagamento ainda não foi capturado.", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  // Na Lista o gesto aparece travado, com o motivo no title.
  await page.getByRole("tab", { name: "Lista" }).click();
  const action = page.getByRole("button", { name: "Aguardando pagamento", exact: true });
  await expect(action).toBeDisabled();
  await expect(action).toHaveAttribute("title", "O pagamento ainda não foi capturado.");
});
