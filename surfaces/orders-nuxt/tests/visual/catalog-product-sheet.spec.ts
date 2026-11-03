import { expect, test, type Page } from "@playwright/test";

// Tabelão de produtos (nome, descrição, preço, peso e fiscal), aberto pelo menu do
// botão Tabelão. Capturas para auditoria, sem baseline.
const CASES = [
  { id: "xl", width: 1440, height: 900 },
  { id: "phone", width: 390, height: 844 },
] as const;

function trackHttpFailures(page: Page): string[] {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 400)
      failures.push(`${response.status()} ${response.request().method()} ${response.url()}`);
  });
  return failures;
}

for (const viewport of CASES) {
  test(`tabelão de produtos · ${viewport.id}`, async ({ page }, testInfo) => {
    const failures = trackHttpFailures(page);
    await page.setViewportSize(viewport);
    await page.goto("/catalog");
    const bulk = page.getByTestId("catalog-bulk-grid");
    await expect(bulk).toBeEnabled({ timeout: 45_000 });
    await bulk.click();
    await page.screenshot({ path: testInfo.outputPath(`menu-${viewport.id}.png`) });
    await page.getByRole("menuitem", { name: /Produtos: nome, preço/ }).click();
    const sheet = page.locator("[data-product-sheet]");
    await expect(sheet).toBeVisible();
    // Edita uma célula com erro (NCM curto) e uma válida, para a captura mostrar os dois.
    const ncm = page.getByRole("textbox", { name: /^NCM de / }).first();
    await ncm.fill("1905");
    await page.getByRole("textbox", { name: /^Preço \(R\$\) de / }).nth(1).fill("12,90");
    await expect(page.locator("[data-cell-problem$='|ncm']").first()).toHaveText("O NCM tem 8 dígitos.");
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: testInfo.outputPath(`sheet-${viewport.id}.png`) });
    expect(failures).toEqual([]);
  });
}
