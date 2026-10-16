import { test, expect } from "@playwright/test";

// Launcher autenticado (mock devolve tiles): a Central renderiza a grade de apps.
test.describe("Central — launcher", () => {
  test("renderiza a saudação e os tiles das superfícies liberadas", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Olá, Ana/i })).toBeVisible();
    // O link do `NuxtPageCard` cobre o cartão por uma camada absoluta: a caixa visível é
    // a do cartão, e o link é conferido pelo nome e pelo destino.
    await expect(page.getByRole("link", { name: /^PDV/ })).toBeAttached();
    await expect(page.getByRole("link", { name: /^Gestor de Pedidos/ })).toBeAttached();
    await expect(page.getByRole("link", { name: /^Loja online/ })).toBeAttached();
    await expect(page.locator("[data-tile-title]:visible")).toHaveCount(5);
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

  test("a pendência mora na linha do app e leva ao item exato; apps com pendência sobem", async ({ page }) => {
    await page.goto("/");

    // "Precisa de você" saiu (dono, 09/10/2026).
    await expect(page.getByRole("heading", { name: /Precisa de você/i })).toHaveCount(0);
    const action = page.getByRole("link", { name: "Abrir pedido: Pedido K7Q2 para aceitar" });
    await expect(action).toHaveAttribute("href", "http://127.0.0.1:3004/WEB-20261003-K7Q2");
    // Botão da suíte (`md`, 32 px; conjunto mínimo da fase 2).
    const box = await action.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(32);
    await expect(page.getByRole("link", { name: "Resolver no contexto: Produção sem insumo suficiente" })).toBeVisible();
    // Os apps com pendência primeiro, na ordem do registro entre si.
    const titles = await page.locator("[data-tile-title]:visible").allInnerTexts();
    expect(titles.map((title) => title.trim())).toEqual(["Gestor de Pedidos", "Produção", "PDV", "Compras", "Loja online"]);
    // A linha de estado continua dizendo o que pede alguém.
    await expect(page.getByText("1 para aceitar").filter({ visible: true })).toBeVisible();
  });

  test("o estado bom acende o ponto verde", async ({ page }) => {
    await page.goto("/");

    // O link do cartão cobre o cartão e leva a linha de estado no nome acessível.
    const pdv = page.getByRole("link", { name: /PDV/i });
    await expect(pdv).toHaveAccessibleName(/Caixa aberto/);
    const card = page.locator('[data-slot="root"][data-orientation]').filter({ has: page.getByRole("link", { name: /^PDV/ }) });
    await expect(card).toContainText("Caixa aberto");
    await expect(card.locator("[data-tile-tone]")).toHaveAttribute("data-tile-tone", "positive");
  });
});
