import { expect, test, type Page } from "@playwright/test";

import {
  expectNoOperatorOverlap,
  waitForAnimationsToSettle,
} from "../../../operator-kit/visual/playwright";

// A trava da sobreposição (dono, 07/11/2026: "não pode acontecer, nem nessa tela nem em
// nenhuma"). Em cada largura da régua e em cada tela da Produção, nada visível se desenha
// por cima de outra coisa visível: controle sobre controle, e texto solto sobre controle
// ou sobre outro texto. É geometria, não retrato: não há baseline.
//
// O spec define as próprias larguras, então roda num project só (chromium-desktop); os
// demais projects da matriz o pulam. As telas abrem no cenário povoado do mock (board,
// QC, pesagem, receitas); os relatórios, no cenário próprio deles.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 375] as const;

const OVERLAP_PROJECT = "chromium-desktop";

const ROUTES: ReadonlyArray<{ path: string; scenario: string }> = [
  { path: "/", scenario: "populated" },
  { path: "/plan", scenario: "populated" },
  { path: "/mise-en-place", scenario: "populated" },
  { path: "/timers", scenario: "populated" },
  { path: "/close", scenario: "populated" },
  { path: "/close?lot=104", scenario: "populated" },
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

// WP-F20 (P1-06, `EV/02`): no tablet deitado de toque, o painel "Quanto está previsto?"
// abre ao lado da lista. Com ele aberto, nada se sobrepõe, o nome de cada lote se lê
// inteiro (a lista encolhe por colunas, nunca pelo nome) e todo alvo tem 44 px.
test.describe("1024 px com o painel do previsto aberto", () => {
  test.use({ viewport: { width: 1024, height: 768 }, hasTouch: true });

  test("a lista e o painel convivem, e o nome se lê inteiro", async ({ context, page }) => {
    await context.addCookies([
      { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" },
      { name: "e2e_scenario", value: "populated", domain: "127.0.0.1", path: "/" },
    ]);
    await page.goto("/");
    await settle(page);
    await page.locator("[data-open-confirm]").first().click();
    await page.locator("[data-open-confirm-panel]").waitFor();
    await settle(page);
    await waitForAnimationsToSettle(page);

    await expectNoOperatorOverlap(page, "/ a 1024 px com o painel do previsto aberto");

    // O nome inteiro: nem cortado na largura, nem escondido pelas duas linhas.
    // A célula do produto guarda pelo menos 96 px (cabe "Croissant" numa linha).
    const cut = await page.locator("[data-open-row] [data-row-product]").evaluateAll((cells) =>
      cells
        .filter((cell) => {
          const name = cell.querySelector<HTMLElement>("[data-row-name]")!;
          return (
            name.scrollWidth > name.clientWidth + 1 ||
            name.scrollHeight > name.clientHeight + 1 ||
            cell.getBoundingClientRect().width < 96
          );
        })
        .map((cell) => cell.querySelector("[data-row-name]")?.textContent?.trim()),
    );
    expect(cut, "nome de lote cortado com o painel aberto").toEqual([]);

    // Alvos de 44 px: as linhas e o painel.
    const small = await page
      .locator("[data-open-table] button, [data-open-confirm-panel] button")
      .evaluateAll((buttons) =>
        buttons
          .filter((button) => {
            const rect = button.getBoundingClientRect();
            return rect.width > 0 && (Math.round(rect.width) < 44 || Math.round(rect.height) < 44);
          })
          .map(
            (button) =>
              `${button.getAttribute("aria-label") || button.textContent?.trim()} ` +
              `${Math.round(button.getBoundingClientRect().width)}×${Math.round(button.getBoundingClientRect().height)}`,
          ),
      );
    expect(small, "alvo menor que 44 px no chão").toEqual([]);
  });
});

// WP-F20 (P1-25, `EV/23`): em pé e no celular, o mesmo teclado da tela, sem o do
// sistema, e alvos de 44 px no diálogo.
for (const viewport of [
  { width: 768, height: 1024 },
  { width: 375, height: 812 },
] as const) {
  test.describe(`${viewport.width} px com o diálogo do previsto aberto`, () => {
    test.use({ viewport, hasTouch: true });

    test("teclado da tela e alvos de 44 px", async ({ context, page }) => {
      await context.addCookies([
        { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" },
        { name: "e2e_scenario", value: "populated", domain: "127.0.0.1", path: "/" },
      ]);
      await page.goto("/");
      await settle(page);
      await page.locator("[data-open-confirm]").first().click();
      const dialog = page.getByRole("dialog");
      await dialog.waitFor();
      await settle(page);
      // O diálogo abre com escala: medir no meio da animação pega o botão encolhido.
      await waitForAnimationsToSettle(page);

      await expect(dialog.getByRole("textbox", { name: "Quantidade prevista" })).toHaveAttribute("inputmode", "none");
      await expect(dialog.getByRole("group", { name: "Teclado numérico de quantidade prevista" })).toBeVisible();
      await expectNoOperatorOverlap(page, `/ a ${viewport.width} px com o diálogo do previsto aberto`);

      const small = await dialog.locator("button").evaluateAll((buttons) =>
        buttons
          .filter((button) => {
            const rect = button.getBoundingClientRect();
            return rect.width > 0 && (Math.round(rect.width) < 44 || Math.round(rect.height) < 44);
          })
          .map((button) => button.getAttribute("aria-label") || button.textContent?.trim()),
      );
      expect(small, "alvo menor que 44 px no diálogo").toEqual([]);
    });
  });
}
