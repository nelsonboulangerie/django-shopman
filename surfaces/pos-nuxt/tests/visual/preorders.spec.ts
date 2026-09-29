import { expect, test, type Page } from "@playwright/test";

const CASES = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
] as const;

async function settle(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
  await page.goto("/preorders");
  await expect(page.locator("[data-week-grid]")).toBeVisible();
  await expect(page.locator("[data-preorder]")).toHaveCount(3);
  await page.evaluate(() => document.fonts.ready);
}

for (const viewport of CASES) {
  test(`Encomendas organizadas em ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await settle(page);
    await expect(page).toHaveScreenshot(`preorders__week__${viewport.width}x${viewport.height}__light.png`, {
      fullPage: true,
    });
  });
}

test("busca prioriza a retirada sem perder o contexto", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await settle(page);
  await page.getByRole("searchbox", { name: /nome, telefone/i }).fill("Ana");
  await expect(page.locator('[data-preorders-results="open"]')).toBeVisible();
  await expect(page).toHaveScreenshot("preorders__search__390x844__light.png", { fullPage: true });
});
