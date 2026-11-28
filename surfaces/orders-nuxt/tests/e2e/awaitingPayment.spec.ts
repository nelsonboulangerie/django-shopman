import { expect, test, type Page } from "@playwright/test";

// DEV-2026-091 (escolha do dono, 25/11/2026): o pedido novo que só espera o Pix ou o
// cartão cair sai da Fila e da coluna Novos e fica recolhido na faixa "Aguardando
// pagamento (N)", no fim. Quando o pagamento cai, ele sobe pedindo o aceite. O cenário
// mora no mock (cookie `e2e_payment=awaiting|paid`). As capturas vão para
// `test-results/dev091/`, para a prévia final.
const REF = "WEB-20261125-0012";
const SHOTS = "test-results/dev091";

async function useScenario(page: Page, baseURL: string, value: "awaiting" | "paid") {
  await page.context().addCookies([{ name: "e2e_payment", value, url: baseURL }]);
}

const band = (page: Page) => page.locator("[data-queue-awaiting-payment]").first();
const toggle = (page: Page) => page.locator("[data-queue-awaiting-payment-toggle]").first();
const row = (page: Page) => page.locator(`[data-queue-awaiting-payment-row="${REF}"]`).first();
const orderCard = (page: Page) => page.locator(`[data-focus-target="order:${REF}"]`);

for (const vp of [
  { name: "375", width: 375, height: 812, url: "/" },
  { name: "desktop-painel", width: 1440, height: 900, url: "/?view=board&columns=all" },
  { name: "desktop-fila", width: 1440, height: 900, url: "/?view=queue" },
]) {
  test.describe(`Aguardando pagamento · ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("sem pagamento: fora dos pedidos, recolhido na faixa", async ({ page, baseURL }) => {
      await useScenario(page, baseURL!, "awaiting");
      await page.goto(vp.url);
      // No celular o Painel abre na aba com trabalho; a faixa mora na aba Novos.
      if (vp.width < 768) await page.getByRole("tab", { name: /^Novos/ }).click();

      await expect(band(page)).toBeVisible();
      await expect(toggle(page)).toContainText("Aguardando pagamento (1)");
      await expect(row(page)).toBeHidden();
      await expect(orderCard(page)).toHaveCount(0);
      await band(page).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${SHOTS}/${vp.name}-recolhida.png` });

      await toggle(page).click();
      await expect(row(page)).toBeVisible();
      await expect(row(page)).toContainText("Ana · R$ 48,70");
      await expect(row(page)).toContainText("Aguardando Pix há 2 min");
      await band(page).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${SHOTS}/${vp.name}-aberta.png` });
    });

    test("o Pix caiu: o pedido sobe pedindo o aceite, e a faixa some", async ({ page, baseURL }) => {
      await useScenario(page, baseURL!, "paid");
      await page.goto(vp.url);

      await expect(orderCard(page).first()).toBeVisible();
      await expect(band(page)).toHaveCount(0);
      await page.screenshot({ path: `${SHOTS}/${vp.name}-pix-caiu.png` });
    });
  });
}
