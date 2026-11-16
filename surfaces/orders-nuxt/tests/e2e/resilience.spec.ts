import { test, expect } from "@playwright/test";

// Banner de conexão (kit) — global no shell, aparece em qualquer estado do Gestor.
test.describe("Gestor — banner de conexão", () => {
  test("aparece ao cair a rede e some ao voltar", async ({ page, context }) => {
    // A Fila escreve os itens numa linha; serve de prova de que a tela carregou.
    await page.goto("/?view=queue");
    await expect(page.getByText("2× Pão · 1× Café")).toBeVisible();

    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);
    await context.setOffline(true);
    await expect(page.getByText(/Sem conexão/i)).toBeVisible();
    await context.setOffline(false);
    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);
  });
});
