import { test, expect } from "@playwright/test";

// Gate de acesso do PDV sem backend de negócio: a leitura do terminal 401a (mock),
// então o app sobe a tela de login no próprio caixa (sem bounce pro Django admin).
test.describe("POS — gate de login (sessão de operador ausente)", () => {
  test("sem sessão, mostra o gate de login com credenciais", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Entre para operar o caixa/i })).toBeVisible();
    await expect(page.getByLabel("Usuário")).toBeVisible();
    await expect(page.getByLabel("Senha")).toBeVisible();
    await expect(page.getByRole("button", { name: /Entrar/i })).toBeVisible();
  });

  // O Entrar não fica apagado esperando os campos: apagado, o toque não dizia o que
  // faltava (beta 05/11, CEN-15). O toque diz, e marca só o campo vazio.
  test("Entrar sem usuário e senha diz o que falta, sem sair da tela", async ({ page }) => {
    await page.goto("/");
    const entrar = page.getByRole("button", { name: /Entrar/i });
    await expect(entrar).toBeEnabled();
    await entrar.click();
    await expect(page.getByText("Informe usuário e senha.").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Entre para operar o caixa/i })).toBeVisible();
  });
});
