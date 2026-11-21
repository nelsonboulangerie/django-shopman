import { expect, test, type Page } from "@playwright/test";

// A corrida da casa na lista de Corridas (M3b, #2898, DEV-2026-030): forma E (letra e cor,
// "2 pedidos", códigos com ∙), quem leva no lugar da fala da TaOn, e os gestos do balcão
// para quando o entregador está sem celular. Gesto que avisa cliente pede confirmação.
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;

type HouseState = { departed: boolean; delivered: string[]; claimed: boolean; gestures: { gesture: string; ref: string; base_revision: string }[] };

async function state(page: Page): Promise<HouseState> {
  return (await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/deliveries/house-ride/`)).json()) as HouseState;
}

test.describe("Entregas: a corrida da casa", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test.beforeEach(async ({ context, page, baseURL }) => {
    await context.addCookies([{ name: "e2e_house", value: "on", url: baseURL! }]);
    await page.request.delete(`${MOCK}/api/v1/backstage/e2e/deliveries/house-ride/`);
    await context.route("https://wa.me/**", (route) => route.fulfill({ status: 200, body: "whatsapp" }));
  });

  test("forma E: letra, 2 pedidos, códigos com ∙ e Diego leva; a TaOn segue como era", async ({ page }) => {
    await page.goto("/delivery");
    const card = page.locator("[data-house-ride]");
    await expect(card).toHaveCount(1);
    await expect(card.locator("[data-house-ride-letter]")).toHaveText("C");
    await expect(card.locator("[data-house-ride-codes]")).toHaveText(/A47\s*∙\s*C03/);
    await expect(card.getByText("2 pedidos", { exact: true })).toBeVisible();
    await expect(card.locator("[data-house-ride-moment]")).toHaveText("Diego leva");
    await expect(card.locator("[data-house-ride-hint]")).toHaveText("Entregador da casa · R$ 15,00 · Abriu o link às 12h31");
    await expect(card).not.toContainText("TaOn");
    // As corridas da TaOn continuam no espelho de sempre.
    await expect(page.locator("[data-ride-mirror]")).toHaveCount(2);
  });

  test("Saiu arma a confirmação e só o segundo toque avança; depois, Entregue por parada", async ({ page }) => {
    await page.goto("/delivery");
    const card = page.locator("[data-house-ride]");
    await card.getByRole("button", { name: "Saiu", exact: true }).click();
    const confirm = card.locator("[data-house-ride-confirm]");
    await expect(confirm).toContainText("Diego saiu com os pedidos? Os clientes recebem o aviso de saída.");
    expect((await state(page)).gestures).toEqual([]);
    await confirm.getByRole("button", { name: "Saiu", exact: true }).click();
    await expect(page.getByText("Rota C: Diego saiu para entrega.", { exact: true })).toBeVisible();
    await expect(card.locator("[data-house-ride-moment]")).toHaveText("Diego na rua · 0 de 2 entregues");

    await card.getByRole("button", { name: "A47 entregue", exact: true }).click();
    await card.locator("[data-house-ride-confirm]").getByRole("button", { name: "A47 entregue", exact: true }).click();
    await expect(card.locator("[data-house-ride-moment]")).toHaveText("Diego na rua · 1 de 2 entregues");
    await expect(card.getByRole("button", { name: "A47 entregue", exact: true })).toHaveCount(0);
    await expect(card.getByRole("button", { name: "C03 entregue", exact: true })).toBeVisible();
    const sent = (await state(page)).gestures;
    expect(sent.map((item) => [item.gesture, item.ref])).toEqual([["depart", ""], ["deliver", "WEB-20261116-0A47"]]);
    expect(sent.every((item) => item.base_revision)).toBe(true);
  });

  test("Reenviar o link abre o WhatsApp com o mesmo link no mesmo toque", async ({ page, context }) => {
    await page.goto("/delivery");
    const popup = context.waitForEvent("page");
    await page.locator("[data-house-ride]").getByRole("button", { name: "Reenviar o link", exact: true }).click();
    const tab = await popup;
    await expect.poll(() => tab.url()).toContain("https://wa.me/5543999990000?text=");
    expect(decodeURIComponent(tab.url())).toContain("Abra o link no seu celular: https://loja.test/rota/tok7");
    await expect(page.getByText("Rota C reenviada para Diego.", { exact: true })).toBeVisible();
  });

  test("Soltar o link pede confirmação e some depois", async ({ page }) => {
    await page.goto("/delivery");
    const card = page.locator("[data-house-ride]");
    await card.getByRole("button", { name: "Soltar o link", exact: true }).click();
    await card.locator("[data-house-ride-confirm]").getByRole("button", { name: "Soltar o link", exact: true }).click();
    await expect(page.getByText("Link de Diego solto. O próximo celular que confirmar fica com ele.", { exact: true })).toBeVisible();
    await expect(card.getByRole("button", { name: "Soltar o link", exact: true })).toHaveCount(0);
  });
});
