import { expect, test } from "@playwright/test";

test("filtro Arquivados mostra somente o produto arquivado e seu selo", async ({ page }, testInfo) => {
  const failedResponses: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });
  await page.goto("/catalog", { waitUntil: "networkidle" });

  await page.screenshot({
    path: testInfo.outputPath("arquivar-superficies-antes-claro.png"),
    fullPage: true,
  });
  await page.evaluate(() => document.documentElement.classList.add("dark"));
  await page.screenshot({
    path: testInfo.outputPath("arquivar-superficies-antes-escuro.png"),
    fullPage: true,
  });
  await page.evaluate(() => document.documentElement.classList.remove("dark"));

  await page.locator("[data-operator-filter-panel-open]").click();
  await page.getByText("Arquivados", { exact: true }).click();
  await page.getByText("Sim", { exact: true }).click();

  await expect(page.getByText("Arquivado", { exact: true })).toBeVisible();
  await expect(page.getByText("Arquivados: Sim", { exact: true })).toBeVisible();

  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-operator-filter-panel]")).toBeHidden();
  await page.screenshot({
    path: testInfo.outputPath("arquivar-superficies-depois-claro.png"),
    fullPage: true,
  });

  await page.evaluate(() => document.documentElement.classList.add("dark"));
  await page.screenshot({
    path: testInfo.outputPath("arquivar-superficies-depois-escuro.png"),
    fullPage: true,
  });
  expect(failedResponses).toEqual([]);
});
