import { expect, test } from "@playwright/test";

test("contagem da vitrine mantém todos os campos dentro da tela de 390px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/session/closing");
  const skip = page.getByRole("button", { name: "Contar a vitrine primeiro" });
  await expect(skip).toBeVisible({ timeout: 90_000 });
  await skip.click();
  const inputs = page.locator("[data-count-input]");
  await expect(inputs.first()).toBeVisible();
  for (const input of await inputs.all()) {
    const box = await input.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  }
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
