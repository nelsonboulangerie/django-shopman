import { test, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição (dono, 07/11/2026: "não pode acontecer, nem nessa tela nem em
// nenhuma"). Em cada largura da régua e em cada tela da Produção, nada visível se desenha
// por cima de outra coisa visível: controle sobre controle, e texto solto sobre controle
// ou sobre outro texto. É geometria, não retrato: não há baseline.
//
// O spec define as próprias larguras, então roda num project só (chromium-desktop); os
// demais projects da matriz o pulam. As telas abrem no cenário povoado do mock (board,
// QC, pesagem, receitas); os relatórios, no cenário próprio deles.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const OVERLAP_PROJECT = "chromium-desktop";

const ROUTES: ReadonlyArray<{ path: string; scenario: string }> = [
  { path: "/", scenario: "populated" },
  { path: "/plan", scenario: "populated" },
  { path: "/mise-en-place", scenario: "populated" },
  { path: "/timers", scenario: "populated" },
  { path: "/close", scenario: "populated" },
  { path: "/quality", scenario: "populated" },
  { path: "/board", scenario: "populated" },
  { path: "/reports", scenario: "reports-populated" },
  { path: "/recipes", scenario: "populated" },
  { path: "/recipes/review", scenario: "populated" },
  { path: "/recipes/new", scenario: "populated" },
  { path: "/recipes/compare", scenario: "populated" },
  { path: "/recipes/pao-frances", scenario: "populated" },
  { path: "/recipes/pao-frances/edit", scenario: "populated" },
];

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
}

test.beforeEach(({}, testInfo) => {
  test.skip(testInfo.project.name !== OVERLAP_PROJECT, `a trava roda as próprias larguras em ${OVERLAP_PROJECT}`);
});

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: width < 768 ? 844 : 900 } });

    for (const route of ROUTES) {
      test(`a tela ${route.path}`, async ({ context, page }) => {
        await context.addCookies([
          { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" },
          { name: "e2e_scenario", value: route.scenario, domain: "127.0.0.1", path: "/" },
        ]);
        await page.goto(route.path);
        await settle(page);
        await expectNoOperatorOverlap(page, `${route.path} a ${width} px`);
      });
    }
  });
}
