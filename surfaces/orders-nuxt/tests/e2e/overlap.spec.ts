import { expect, test, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição (dono, 07/11/2026, no cabeçalho do pedido: "parece coisa de
// amador; não pode acontecer, nem nessa tela nem em nenhuma"). Em cada largura da régua
// e em cada tela do Gestor, nada visível se desenha por cima de outra coisa visível:
// controle sobre controle, e texto solto (título, selo de status, hora, "2 de 4") sobre
// controle ou sobre outro texto. É geometria, não retrato: não há baseline.
//
// 1360 é a largura do defeito (o desktop do dono); 1024 é o tablet deitado com a barra
// lateral, onde a busca inteira não cabe ao lado do título e das ações.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const ROUTES = [
  "/",
  "/?view=board",
  "/history",
  "/catalog",
  "/customers",
  "/customers/groups",
  "/customers/merges",
  "/feeds",
  "/workstations",
  "/settings",
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

    test("o detalhe do pedido, vindo da fila (com anterior e próximo)", async ({ page }) => {
      await page.goto("/");
      // A fila grava a trilha: o detalhe aberto dela ganha "Pedido anterior" e "Próximo".
      for (const ref of ["WEB-20260625-0007", "WEB-20260625-0008"]) {
        await page.locator(`a[href$='/${ref}']`).first().click();
        await page.waitForURL(new RegExp(`/${ref}$`));
        await settle(page);
        if (width >= 768) {
          await expect(page.locator("[data-operator-record-nav]").filter({ visible: true }).first()).toBeVisible();
        }
        await expectNoOperatorOverlap(page, `${ref} a ${width} px`);
        await page.goto("/");
      }
    });

    for (const route of ROUTES) {
      test(`a tela ${route}`, async ({ page }) => {
        await page.goto(route);
        await settle(page);
        await expectNoOperatorOverlap(page, `${route} a ${width} px`);
      });
    }
  });
}
