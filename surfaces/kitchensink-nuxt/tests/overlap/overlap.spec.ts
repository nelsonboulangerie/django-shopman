import { test, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição no catálogo do kit (dono, 07/11/2026: "não pode acontecer, nem
// nessa tela nem em nenhuma"). O catálogo mostra cada peça do operator-kit em cada estado,
// e o shell de referência (/suite) monta a moldura como um app de verdade monta: o que se
// sobrepõe aqui se sobrepõe em todos os apps. Em cada largura da régua, nada visível se
// desenha por cima de outra coisa visível. É geometria, não retrato: não há baseline.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const STATES = [
  "loading",
  "empty",
  "error",
  "offline",
  "reconnecting",
  "slow-network",
  "readonly",
  "forbidden",
  "success",
  "extreme-content",
] as const;

const ROUTES = [
  "/",
  "/?mode=operational",
  ...STATES.map((state) => `/?state=${state}`),
  "/suite",
  "/suite?alerts=none",
  "/suite?alerts=three",
] as const;

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
}

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: width < 768 ? 844 : 900 } });

    for (const route of ROUTES) {
      test(`a tela ${route}`, async ({ page }) => {
        await page.goto(route);
        await page
          .locator('[data-hydrated="true"]')
          .first()
          .waitFor({ state: "attached" });
        await settle(page);
        await expectNoOperatorOverlap(page, `${route} a ${width} px`);
      });
    }
  });
}
