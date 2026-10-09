import { test, expect } from "@playwright/test";

// Gate de operador (Opção C, Camada 1), split operador-vs-público e roteamento — o mock
// ramifica pelo cookie `e2e_session` que o BFF encaminha. Login efetivo/lock/ações com
// dados reais = reviewer local.

const authed = { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" };

test.describe("KDS — gate de operador", () => {
  test("device não autenticado → tela de login (sem sessão)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toBeVisible();
    await expect(page.getByLabel("Usuário")).toBeVisible();
    await expect(page.getByLabel("Senha")).toBeVisible();
  });

  test("sessão autenticada → estações + rail da suíte (kit), sem login", async ({ page, context }) => {
    await context.addCookies([authed]);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Estações" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toHaveCount(0);
    await expect(page.locator("aside[data-suite-rail]")).toBeVisible();
  });

  test("navegação pelas estações reais: a bancada pelo nome, Saída no Gestor, sem item Preparo", async ({ page, context }) => {
    await context.addCookies([authed]);
    await page.goto("/bancada");
    const rail = page.locator("aside[data-suite-rail]");
    await expect(rail.locator('[data-section="station:bancada"]')).toHaveAttribute("href", "/bancada");
    await expect(rail.locator('[data-section="station:bancada"]')).toHaveAttribute("aria-current", "page");
    await expect(rail.locator('[data-section="exit"]')).toHaveAttribute("href", /\?columns=expedition$/);
    await expect(rail.getByText("Preparo", { exact: true })).toHaveCount(0);
  });
});

test.describe("KDS — split operador vs público", () => {
  test("/pickup é PÚBLICO: renderiza o painel do cliente sem login e FORA do rail", async ({ page }) => {
    // Sem cookie de sessão — o /pickup não é embrulhado pelo gate nem pelo rail.
    await page.goto("/pickup");
    await expect(page.getByRole("heading", { name: "Seu pedido" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toHaveCount(0);
    await expect(page.locator("aside[data-suite-rail]")).toHaveCount(0);
  });
});

// NOTA: o KDS NÃO tem 404 para path de um segmento — `pages/[ref].vue` é a rota dinâmica
// da estação, então `/qualquer-coisa` resolve como um ref de estação (válido, tenta o
// board), não um 404. Sem catch-all de erro genérico para exercitar aqui (análogo ao POS,
// view única). O gate de login e o split público cobrem os guards que importam.
