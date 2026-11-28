import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição (dono, 07/11/2026: "não pode acontecer, nem nessa tela nem em
// nenhuma"). Em cada largura da régua e em cada tela do PDV, nada visível se desenha por
// cima de outra coisa visível. É geometria, não retrato: não há baseline.
//
// O balcão é o do mock da venda (cookie `pos_e2e=offline-sale`, ver `mockBackend.mjs`):
// operadora com sessão, comandas em uso, encomendas, caixa e ajustes. A venda é coberta
// vazia, com a comanda 12 (três linhas) e com a 13 (nove linhas, nomes compridos).
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const ROUTES = [
  "/",
  "/preorders",
  "/preorders/NB-1042",
  "/preorders/NB-1054",
  "/session",
  "/session/report",
  "/session/closing",
  "/settings/terminal",
  "/settings/printers",
  "/settings/card-machines",
  "/settings/kitchen",
  "/settings/seating",
  "/settings/shortcuts",
  "/display",
] as const;

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
}

async function useSaleCounter(context: BrowserContext, baseURL: string) {
  await context.addCookies([{ name: "pos_e2e", value: "offline-sale", url: baseURL }]);
}

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: width < 768 ? 844 : 900 } });

    for (const tab of ["12", "13"] as const) {
      test(`a venda com a comanda #${tab} aberta`, async ({ page, context, baseURL }) => {
        await useSaleCounter(context, baseURL!);
        await page.goto("/");
        await page.getByText(`#${tab}`, { exact: true }).last().click();
        await expect(page.getByRole("heading", { name: `#${tab}`, level: 1 })).toBeVisible();
        // Abaixo de 1024 a comanda é folha de baixo: primeiro a grade com a barra da
        // venda, depois a folha aberta.
        if (width < 1024) {
          await settle(page);
          await expectNoOperatorOverlap(page, `comanda #${tab} fechada a ${width} px`);
          await page.getByRole("button", { name: "Ver a comanda" }).click();
          await expect(page.getByRole("dialog", { name: new RegExp(`^#${tab} `) })).toBeVisible();
        } else {
          await expect(page.getByRole("button", { name: /Pagamento/ }).first()).toBeEnabled();
        }
        await settle(page);
        await expectNoOperatorOverlap(page, `comanda #${tab} a ${width} px`);
      });
    }

    for (const route of ROUTES) {
      test(`a tela ${route}`, async ({ page, context, baseURL }) => {
        await useSaleCounter(context, baseURL!);
        await page.goto(route);
        await settle(page);
        await expectNoOperatorOverlap(page, `${route} a ${width} px`);
      });
    }
  });
}
