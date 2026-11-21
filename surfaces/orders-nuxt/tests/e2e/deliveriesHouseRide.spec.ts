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
    await context.addCookies([{ name: "e2e_house", value: "on", url: baseURL! }, { name: "e2e_ns", value: "house-ride", url: baseURL! }]);
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

  test("Imprimir a via sem impressora diz o motivo e não mexe na corrida (#2406)", async ({ page }) => {
    await page.goto("/delivery");
    const card = page.locator("[data-house-ride]");
    await card.getByRole("button", { name: "Imprimir a via", exact: true }).click();
    await expect(page.getByText("Este dispositivo não tem impressora. A via sai no dispositivo que tem impressora.")).toBeVisible();
    await expect(card.locator("[data-house-ride-moment]")).toHaveText("Diego leva");
    expect((await state(page)).gestures.map((item) => item.gesture)).toEqual(["slip"]);
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

  test("o cartão liga para o entregador da casa", async ({ page }) => {
    await page.goto("/delivery");
    const call = page.locator("[data-house-ride]").getByRole("link", { name: "Ligar para Diego" });
    await expect(call).toHaveAttribute("href", "tel:43999990000");
  });

  // M3d (#2937): o detalhe da corrida da casa diz quem leva, tem os gestos do balcão e o
  // "Ligar para Diego", e nada do que só a TaOn tem.
  test("o detalhe da corrida da casa: quem leva, os gestos e nada da TaOn", async ({ page }) => {
    await page.goto("/delivery?ride=CASA-7F3A2B");
    const detail = page.locator("[data-ride-detail]");
    await expect(detail.locator("[data-ride-detail-title]")).toHaveText("Corrida C · Diego leva");
    await expect(detail.getByText("Entregador da casa · R$ 15,00 · Abriu o link às 12h31", { exact: true })).toBeVisible();
    await expect(detail.locator("[data-ride-detail-house]").getByRole("button", { name: "Saiu", exact: true })).toBeVisible();
    await expect(detail.locator("[data-ride-detail-house]").getByRole("button", { name: "Reenviar o link", exact: true })).toBeVisible();
    await expect(detail.locator("[data-ride-driver-call]")).toHaveText("Ligar para Diego");
    await expect(detail).not.toContainText("TaOn");
    await expect(detail.locator("[data-ride-position-source]")).toHaveCount(0);

    await detail.locator("[data-ride-detail-house]").getByRole("button", { name: "Saiu", exact: true }).click();
    await detail.locator("[data-house-ride-confirm]").getByRole("button", { name: "Saiu", exact: true }).click();
    await expect(page.getByText("Rota C: Diego saiu para entrega.", { exact: true })).toBeVisible();
    await expect(detail.locator("[data-ride-detail-title]")).toHaveText("Corrida C · Diego na rua · 0 de 2 entregues");
    expect((await state(page)).gestures.map((item) => item.gesture)).toEqual(["depart"]);
  });

  test("na Saída dos Pedidos, a corrida da casa é UM cartão no lugar dos pedidos dela", async ({ page }) => {
    await page.goto("/?view=board&columns=all");
    const exit = page.locator('[data-zone="expedition"]');
    const card = exit.locator("[data-exit-house-ride]");
    await expect(card).toHaveCount(1);
    await expect(card.locator("[data-house-ride-codes]")).toHaveText(/A47\s*∙\s*C03/);
    await expect(card.locator("[data-house-ride-moment]")).toHaveText("Diego leva");
    // O pedido solto segue no cartão de sempre; os da corrida não aparecem soltos.
    await expect(exit.locator("[data-card-who]").filter({ hasText: "Edu" })).toHaveCount(1);
    await expect(exit.locator("[data-card-who]").filter({ hasText: "Ana" })).toHaveCount(0);
    await card.getByRole("button", { name: "Saiu", exact: true }).click();
    await card.locator("[data-house-ride-confirm]").getByRole("button", { name: "Saiu", exact: true }).click();
    await expect(page.getByText("Rota C: Diego saiu para entrega.", { exact: true })).toBeVisible();
    await expect(card.locator("[data-house-ride-moment]")).toHaveText("Diego na rua · 0 de 2 entregues");
  });
});
