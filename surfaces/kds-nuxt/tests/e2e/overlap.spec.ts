import { test, type BrowserContext, type Page } from "@playwright/test";

import { expectNoOperatorOverlap } from "../../../operator-kit/visual/playwright";

// A trava da sobreposição (dono, 07/11/2026: "não pode acontecer, nem nessa tela nem em
// nenhuma"). Em cada largura da régua e em cada tela da Cozinha, nada visível se desenha
// por cima de outra coisa visível: controle sobre controle, e texto solto sobre controle
// ou sobre outro texto. É geometria, não retrato: não há baseline.
//
// As estações cheias vêm dos quadros da prévia (cookie `e2e_kds=preview` no mock): a
// Bancada com a fila, os Cafés com a mudança com alarde e o pedido cancelado. As vazias
// (Lanches, Encomendas, Saída) mostram o quadro sem ticket. O login e o painel público
// do cliente (`/pickup`) entram sem sessão.
const WIDTHS = [1440, 1360, 1280, 1024, 768, 390] as const;

const authed = { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" };
const preview = { name: "e2e_kds", value: "preview", domain: "127.0.0.1", path: "/" };

const OPERATOR_ROUTES = ["/", "/bancada", "/cafes", "/lanches", "/encomendas", "/saida"] as const;
const PUBLIC_ROUTES = [
  { path: "/", name: "o login (sem sessão)" },
  { path: "/pickup", name: "o painel do cliente /pickup" },
] as const;

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
}

async function signIn(context: BrowserContext) {
  await context.addCookies([authed, preview]);
}

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: width < 768 ? 844 : 900 } });

    for (const route of OPERATOR_ROUTES) {
      test(`a tela ${route}`, async ({ page, context }) => {
        await signIn(context);
        await page.goto(route);
        await settle(page);
        await expectNoOperatorOverlap(page, `${route} a ${width} px`);
      });
    }

    test("a Bancada sem ticket (quadro vazio)", async ({ page, context }) => {
      await context.addCookies([authed]);
      await page.goto("/bancada");
      await settle(page);
      await expectNoOperatorOverlap(page, `/bancada vazia a ${width} px`);
    });

    for (const route of PUBLIC_ROUTES) {
      test(route.name, async ({ page }) => {
        await page.goto(route.path);
        await settle(page);
        await expectNoOperatorOverlap(page, `${route.name} a ${width} px`);
      });
    }
  });
}
