import { expect, test, type Page } from "@playwright/test";

const CASES = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
] as const;

async function settle(page: Page) {
  // O mesmo dia do mock (`MOCK_TODAY`): o Período da tela parte do relógio do navegador.
  await page.clock.setFixedTime(new Date("2026-09-29T12:00:00"));
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
  await page.goto("/preorders");
  await expect(page.locator("[data-preorder]:visible").first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

for (const viewport of CASES) {
  test(`Encomendas organizadas em ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await settle(page);
    const mode = viewport.width < 640 ? "day" : "week";
    if (mode === "day") {
      await expect(page.locator("[data-preorders-day] [data-preorder]:visible")).toHaveCount(2);
    } else {
      await expect(page.locator("[data-week-board] [data-preorder]:visible")).toHaveCount(3);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const firstCard = await page.locator("[data-preorder]:visible").first().boundingBox();
    expect(firstCard?.height || 0).toBeGreaterThanOrEqual(44);
    await expect(page).toHaveScreenshot(`preorders__${mode}__${viewport.width}x${viewport.height}__light.png`, {
      fullPage: true,
    });
  });
}

test("busca prioriza a retirada sem perder o contexto", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await settle(page);
  // "Cliente veio buscar" é a busca da tela no cabeçalho: abre com o `/`, e o que
  // se digita filtra a própria tela (o alcance "Esta tela").
  await page.keyboard.press("/");
  const palette = page.getByRole("textbox", {
    name: "Nome, telefone, CPF ou CNPJ, endereço ou número do pedido",
  });
  await expect(palette).toBeFocused();
  await palette.fill("Ana");
  await page.getByRole("option", { name: "Filtrar as encomendas por “Ana”" }).click();
  await expect(page.locator('[data-preorders-results="open"]')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page).toHaveScreenshot("preorders__search__390x844__light.png", { fullPage: true });
});
