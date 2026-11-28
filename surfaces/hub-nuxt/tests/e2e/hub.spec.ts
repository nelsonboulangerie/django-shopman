import { test, expect } from "@playwright/test";

// Launcher autenticado (mock devolve tiles): a Central é uma grade de ícones, cada app com
// o nome e, só quando algo espera um gesto de quem opera, o número no canto do ícone.
test.describe("Central — launcher", () => {
  test("renderiza a saudação e os ícones das superfícies liberadas", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Olá, Ana/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^PDV/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Gestor de Pedidos/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Loja online/ })).toBeVisible();
    await expect(page.locator("[data-tile-title]:visible")).toHaveCount(5);
  });

  test("cada ícone linka pra sua superfície; a Loja (config) abre em nova aba", async ({ page }) => {
    await page.goto("/");

    const pos = page.getByRole("link", { name: /PDV/i });
    await expect(pos).toHaveAttribute("href", "http://127.0.0.1:3002/");
    await expect(pos).toHaveAttribute("target", "_self");

    const storeLink = page.getByRole("link", { name: "Loja online. Abre em outra janela" });
    await expect(storeLink).toHaveAttribute("href", "/admin/shop/shop/");
    await expect(storeLink).toHaveAttribute("target", "_blank");
  });

  test("o número no canto do ícone só onde algo espera um gesto, com nome falado", async ({ page }) => {
    await page.goto("/");

    // A ordem é a do registro, sempre (o ícone não troca de lugar com a pendência).
    const titles = await page.locator("[data-tile-title]:visible").allInnerTexts();
    expect(titles.map((title) => title.trim())).toEqual(["PDV", "Gestor de Pedidos", "Compras", "Produção", "Loja online"]);

    const gestor = page.getByRole("link", { name: "Gestor de Pedidos, 1 para aceitar" });
    await expect(gestor).toHaveAttribute("data-attention", "1");
    await expect(gestor.getByText("1", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Produção, 1 aviso" })).toBeVisible();
    // Em dia, nada: só o nome.
    await expect(page.getByRole("link", { name: "PDV", exact: true })).not.toHaveAttribute("data-attention", /.+/);
    // O que saiu não volta: linha de estado, pendência, ponto.
    await expect(page.getByText("11 ativos")).toHaveCount(0);
    await expect(page.getByText("Pedido K7Q2 para aceitar")).toHaveCount(0);
  });
});
