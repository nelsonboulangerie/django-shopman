import { test, expect } from "@playwright/test";

test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

test("agendamento e entrega iFood ficam legíveis no celular", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.getByRole("searchbox").fill("IFOOD-SCHEDULED");
  await expect(page.getByText("Entrega por entregador iFood", { exact: true })).toBeVisible();
  await expect(page.getByText("Início do preparo: 14/09/2026 às 15:15", { exact: true })).toBeVisible();
  await expect(page.getByText("Fim da janela: 14/09/2026 às 16:30", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Aguardando horário iFood", exact: true })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("ifood-mobile.png"), fullPage: true });
});
