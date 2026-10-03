import { test, expect } from "@playwright/test";

// Launcher autenticado (mock devolve tiles): a Central renderiza a grade de apps.
test.describe("Central — launcher", () => {
  test("renderiza a saudação e os tiles das superfícies liberadas", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Olá, Ana/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /PDV/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Gestor de Pedidos/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Loja online/i })).toBeVisible();
  });

  test("cada tile linka pra sua superfície; a Loja (config) abre em nova aba", async ({ page }) => {
    await page.goto("/");

    const pos = page.getByRole("link", { name: /PDV/i });
    await expect(pos).toHaveAttribute("href", "http://127.0.0.1:3002/");
    await expect(pos).toHaveAttribute("target", "_self");

    const storeLink = page.getByRole("link", { name: /Loja online/i });
    await expect(storeLink).toHaveAttribute("href", "/admin/shop/shop/");
    await expect(storeLink).toHaveAttribute("target", "_blank");
  });

  test("Precisa de você vem no topo, com o gesto que abre o lugar exato", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Precisa de você/i })).toBeVisible();
    const action = page.getByRole("link", { name: "Abrir pedido: Pedido K7Q2 para aceitar" });
    await expect(action).toHaveAttribute("href", "http://127.0.0.1:3004/WEB-20261003-K7Q2");
    // Alvo de toque de 48 px.
    const box = await action.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(48);
    await expect(page.getByText("Mais 2 esperando nos apps abaixo.")).toBeVisible();
    // A linha de estado do bloco concorda com a fila.
    await expect(page.getByText("1 para aceitar")).toBeVisible();
  });
});
