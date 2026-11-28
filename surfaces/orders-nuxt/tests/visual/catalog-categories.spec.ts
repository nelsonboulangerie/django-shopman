import { expect, test, type Page } from "@playwright/test";

const CASES = [
  { id: "md", width: 768, height: 900 },
  { id: "xl", width: 1440, height: 900 },
] as const;
const THEMES = ["light", "dark"] as const;

function trackHttpFailures(page: Page): string[] {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 400)
      failures.push(
        `${response.status()} ${response.request().method()} ${response.url()}`,
      );
  });
  return failures;
}

for (const viewport of CASES) {
  for (const theme of THEMES) {
    test(`categorias do iFood · ${viewport.id} · ${theme}`, async ({
      page,
    }, testInfo) => {
      const failures = trackHttpFailures(page);
      await page.setViewportSize(viewport);
      await page.addInitScript(
        ([value, key]) => {
          localStorage.setItem("nuxt-color-mode", value);
          localStorage.setItem(key, value);
        },
        [theme, "orders-nuxt-color-mode"],
      );
      await page.goto("/channels/ifood/catalog");
      await expect(
        page.getByRole("heading", { name: "Categorias do iFood" }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Pães artesanais", exact: true }),
      ).toBeVisible();
      await expect(page.locator("html")).toHaveClass(
        theme === "dark" ? /dark/ : /light/,
      );
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({
        path: testInfo.outputPath(
          `ifood-categories-${viewport.id}-${theme}.png`,
        ),
        fullPage: true,
      });
      expect(failures).toEqual([]);
    });
  }
}
