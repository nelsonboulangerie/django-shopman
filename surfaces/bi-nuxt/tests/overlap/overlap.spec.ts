import { test, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição no B.I. (dono, 07/11/2026: "não pode acontecer, nem nessa tela
// nem em nenhuma"). Em cada largura da régua e em cada tela do B.I., nada visível se
// desenha por cima de outra coisa visível. É geometria, não retrato: não há baseline.
// O backend é o mock gravado da matriz visual, no cenário normal.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const BACKEND = "http://127.0.0.1:" + (process.env.BI_OVERLAP_BACKEND_PORT || "41807");

const ROUTES = [
  "/",
  "/?view=lots",
  "/sales",
  "/cash",
  "/customers",
  "/profiles",
  "/explore",
  "/forecast",
  "/scenarios",
  "/delivery",
] as const;

test.beforeAll(async ({ request }) => {
  await request.get(BACKEND + "/__visual/scenario?set=normal");
});

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
}

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: width < 768 ? 844 : 900 } });

    for (const route of ROUTES) {
      test(`a tela ${route}`, async ({ page }) => {
        await page.goto(route);
        await settle(page);
        await expectNoOperatorOverlap(page, `${route} a ${width} px`);
      });
    }
  });
}
