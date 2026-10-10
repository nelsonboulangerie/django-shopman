import { expect, test } from "@playwright/test";

// Prova mínima da matriz do B.I.: as 8 telas abrem no cenário normal do mock
// gravado, com o título da página no ar e sem erro de página no console.
// Sem baseline de retrato: a captura com `toHaveScreenshot` só entra quando a
// matriz rodar no browser da CI (regra do CLAUDE.md sobre retratos).

const BACKEND = "http://127.0.0.1:" + (process.env.BI_VISUAL_BACKEND_PORT || "38794");

const ROUTES = ["/", "/?view=lots", "/sales", "/cash", "/customers", "/profiles", "/explore", "/forecast", "/scenarios"];

test.beforeAll(async ({ request }) => {
  await request.get(BACKEND + "/__visual/scenario?set=normal");
});

for (const route of ROUTES) {
  test("bi " + route + " abre no cenário normal", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    const response = await page.goto(route);
    expect(response?.status()).toBeLessThan(500);
    await expect(page.locator("h1").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(pageErrors).toEqual([]);
  });
}
