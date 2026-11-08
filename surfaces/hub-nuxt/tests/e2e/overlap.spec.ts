import { expect, test, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição (dono, 07/11/2026: "não pode acontecer, nem nessa tela nem em
// nenhuma"). Em cada largura da régua, nada visível da Central se desenha por cima de outra
// coisa visível: controle sobre controle, e texto solto (saudação, hora, marca, nome do app,
// número no canto do ícone) sobre controle ou sobre outro texto. É geometria, não retrato:
// não há baseline.
//
// A Central é uma tela só (o launcher em `app.vue`); cobrimos ela em dia de trabalho
// (com números nos ícones) e com o aviso de conexão caída por cima do cabeçalho.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

// O canal de avisos (SSE do kit) reconecta contra o mock, que não fala SSE: a rede às vezes
// não fica 500 ms quieta. A tela já está desenhada (o teste espera o ícone antes), então
// "rede quieta" é um teto curto, não uma condição.
async function settle(page: Page) {
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
}

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: width < 768 ? 844 : 900 } });

    test("a tela /", async ({ page }) => {
      await page.goto("/");
      await expect(page.locator("[data-hub-app-link]").first()).toBeVisible();
      await settle(page);
      await expectNoOperatorOverlap(page, `/ a ${width} px`);
    });

    test("a tela / sem conexão", async ({ page, context }) => {
      await page.goto("/");
      await expect(page.locator("[data-hub-app-link]").first()).toBeVisible();
      await settle(page);
      await context.setOffline(true);
      await expect(page.getByText(/Sem conexão/i)).toBeVisible();
      await page.evaluate(
        () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
      );
      await expectNoOperatorOverlap(page, `/ sem conexão a ${width} px`);
      await context.setOffline(false);
    });
  });
}
