import { expect, test, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição no Compras, no molde do Gestor: em cada largura da régua e em
// cada tela, nada visível se desenha por cima de outra coisa visível (controle sobre
// controle, texto solto sobre controle ou sobre outro texto). É geometria, não retrato:
// não há baseline. O backend é o mock hermético da matriz visual; o cenário é trocado
// nele antes de cada navegação.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const BACKEND = "http://127.0.0.1:" + (process.env.PURCHASE_OVERLAP_BACKEND_PORT || "41808");

const SCREENS = [
  { route: "/", scenario: "normal", ready: "[data-purchase-panel]" },
  { route: "/", scenario: "error", ready: "[data-purchase-load-error]" },
  { route: "/buy", scenario: "normal", ready: "[data-buy-row]" },
  { route: "/receive", scenario: "normal", ready: "[data-receipt-key-entry]" },
  { route: "/receive", scenario: "receiving", ready: "[data-receive]" },
  { route: "/count", scenario: "normal", ready: "[data-count-table]" },
  { route: "/base/materials", scenario: "normal", ready: "[data-base-table]" },
  { route: "/base/materials", scenario: "empty", ready: "[data-base-materials]" },
  { route: "/base/materials/MANTEIGA-82", scenario: "normal", ready: "[data-material-panel]" },
  { route: "/base/suppliers", scenario: "normal", ready: "[data-base-suppliers-table]" },
  { route: "/base/suppliers/LATICINIOS-SERRA", scenario: "normal", ready: "[data-supplier-panel]" },
  { route: "/base/costs", scenario: "normal", ready: "[data-cost-batch]" },
] as const;

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

    for (const screen of SCREENS) {
      test(`a tela ${screen.route} (${screen.scenario})`, async ({ page, request }) => {
        await request.get(BACKEND + "/__visual/scenario?set=" + screen.scenario);
        await page.goto(screen.route);
        await expect(page.locator("[data-purchase-app]")).toBeVisible();
        await expect(page.locator(screen.ready).first()).toBeAttached();
        await settle(page);
        await expectNoOperatorOverlap(page, `${screen.route} (${screen.scenario}) a ${width} px`);
      });
    }
  });
}
