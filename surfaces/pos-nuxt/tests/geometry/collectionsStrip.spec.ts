import { expect, test, type Page } from "@playwright/test";

// Retrato opcional para auditar à mão: `POS_CAPTURE_DIR=<pasta> npx playwright test ...`.
async function capture(page: Page, name: string) {
  if (process.env.POS_CAPTURE_DIR) await page.screenshot({ path: `${process.env.POS_CAPTURE_DIR}/${name}` });
}

// A faixa das coleções da Venda (dono, 03/11/2026): com mouse, as coleções que não
// cabem ficavam fora de alcance (barra escondida, roda rolando para baixo). Agora há
// setas quando há mais daquele lado, a roda rola a faixa, e a última se alcança.
for (const size of [{ width: 1024, height: 700 }, { width: 1366, height: 768 }] as const) {
  test(`coleções alcançáveis com mouse em ${size.width}`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await page.getByRole("button", { name: /#13/ }).first().click();
    const strip = page.locator("[data-pos-collections]");
    await expect(strip).toBeVisible();
    const overflow = await strip.evaluate((el) => el.scrollWidth > el.clientWidth + 1);
    const forward = page.locator("[data-pos-collections-forward]");
    const back = page.locator("[data-pos-collections-back]");
    await capture(page, `faixa-${size.width}.png`);
    if (!overflow) {
      await expect(forward).toHaveCount(0);
      await expect(back).toHaveCount(0);
      return;
    }
    await expect(forward).toBeEnabled();
    await expect(back).toBeDisabled();
    const before = await strip.evaluate((el) => el.clientWidth);
    // A roda vertical do mouse rola a faixa para o lado.
    await strip.hover();
    await page.mouse.wheel(0, 200);
    await expect.poll(() => strip.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
    await expect(back).toBeEnabled();
    // A seta leva até o fim, e a última coleção fica à vista.
    for (let i = 0; i < 10 && (await forward.isEnabled()); i += 1) {
      await forward.click();
      await page.waitForTimeout(400);
    }
    await expect(forward).toBeDisabled();
    // A faixa não muda de largura no caminho (as setas não somem).
    expect(await strip.evaluate((el) => el.clientWidth)).toBe(before);
    await expect(strip.locator("button").last()).toBeInViewport();
    await capture(page, `faixa-${size.width}-fim.png`);
  });
}
