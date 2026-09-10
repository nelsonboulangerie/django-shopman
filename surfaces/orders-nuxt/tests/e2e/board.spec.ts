import { test, expect } from "@playwright/test";

// Board autenticado (mock devolve sessão + fila): o Gestor passa dos gates e renderiza
// o card do pedido com cliente, itens e total.
test.describe("Gestor — board de pedidos", () => {
  test("sessão autenticada + fila → renderiza o card", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("2× Pão · 1× Café")).toBeVisible();
    await expect(page.getByText("R$ 15,00")).toBeVisible();
    await expect(page.getByText("Ana", { exact: true })).toBeVisible();
  });

  test("indicador de tempo-real: sem SSE (origem do mock) → 'Atualização automática'", async ({ page }) => {
    await page.goto("/");
    // O mock é outra origem (:8796 ≠ :3004) → SSE não conecta → sinal honesto de poll.
    await expect(page.getByText("Atualização automática")).toBeVisible();
    await expect(page.getByText("Ao vivo")).toHaveCount(0);
  });
});


test("card e tabela mantêm o avanço bloqueado e explicam o motivo", async ({ page }) => {
  await page.goto("/");
  const action = page.getByRole("button", { name: "Aguardando pagamento", exact: true });
  await expect(action).toBeDisabled();
  await expect(action).toHaveAttribute("title", "O pagamento ainda não foi capturado.");
  await page.getByTitle("Tabela (atalho: v)").click();
  await expect(action).toBeDisabled();
  await expect(action).toHaveAttribute("title", "O pagamento ainda não foi capturado.");
});
