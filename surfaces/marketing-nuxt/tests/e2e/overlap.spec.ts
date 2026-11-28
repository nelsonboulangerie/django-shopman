import { test, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição (dono, 07/11/2026: "não pode acontecer, nem nessa tela nem em
// nenhuma"). Em cada largura da régua e em cada tela do Marketing, nada visível se
// desenha por cima de outra coisa visível: controle sobre controle, e texto solto sobre
// controle ou sobre outro texto. É geometria, não retrato: não há baseline.
//
// O cenário é o cookie `visual_scenario` do backend hermético: escolhe-se o que deixa a
// tela cheia (fila com decisão, detalhe com ação de conferência), não o vazio.
// Fica de fora `/second-control/<ref>`: o backend hermético não serve o pedido de
// confirmação (responde 404), então a tela só mostraria o próprio vazio.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const SCREENS = [
  ["/", "board-pending"],
  ["/scheduled", "board-pending"],
  ["/history", "board-normal"],
  ["/settings", "board-normal"],
  ["/settings/campaigns", "campaigns-dense"],
  ["/settings/templates", "board-normal"],
  ["/settings/platforms", "board-normal"],
  ["/settings/offers", "board-normal"],
  ["/announcements/41", "detail-pending"],
  ["/announcements/41", "detail-unknown"],
  ["/announcements/41", "detail-partial"],
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

    for (const [route, scenario] of SCREENS) {
      test(`a tela ${route} (${scenario})`, async ({ page }) => {
        await page.context().addCookies([
          { name: "visual_scenario", value: scenario, domain: "127.0.0.1", path: "/" },
        ]);
        await page.goto(route);
        await settle(page);
        await expectNoOperatorOverlap(page, `${route} (${scenario}) a ${width} px`);
      });
    }
  });
}
