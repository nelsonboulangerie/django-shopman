import { expect, test, type Page } from "@playwright/test";

// Cancelar a corrida da TaOn, na tela de verdade (revisão das Entregas, F1a).
// O cenário mora no mock (`mockBackend.mjs`, ligado pelo cookie `e2e_deliveries`):
// quatro corridas, uma por estado do cancelamento. O que estas provas travam:
//  - um toque NUNCA cancela (nem na seção Entregas, nem no Painel do pedido);
//  - antes do aceite, uma confirmação; depois do aceite, o motivo é o botão e vai
//    à TaOn como `reason_id`;
//  - o cancelamento pedido e a recusa da TaOn aparecem, e o pedido tira o botão.
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;
const COOKIE = { cookie: "e2e_deliveries=cancel" };

async function sent(page: Page): Promise<{ key: string; reason_id: number | null }[]> {
  const response = await page.request.get(`${MOCK}/api/v1/backstage/e2e/deliveries/sent/`, { headers: COOKIE });
  return (await response.json()).sent;
}

test.beforeEach(async ({ context, page, baseURL }) => {
  await context.addCookies([{ name: "e2e_deliveries", value: "cancel", url: baseURL! }]);
  await page.request.get(`${MOCK}/api/v1/backstage/e2e/deliveries/reset/`, { headers: COOKIE });
});

test.describe("Entregas: cancelar a corrida", () => {
  test("antes do aceite: um toque arma, o segundo confirma, e o pedido aparece na tela", async ({ page }) => {
    await page.goto("/deliveries?ride=776753301");
    const detail = page.locator("[data-ride-detail]");
    await detail.locator("[data-ride-cancel]").click();
    expect(await sent(page)).toEqual([]);
    const confirm = detail.locator("[data-courier-cancel-confirm]");
    await expect(confirm).toContainText("Cancelar a corrida A? A05 e C12 voltam para Aguardando.");
    await expect(confirm.locator("[data-courier-cancel-reason]")).toHaveCount(0);

    await confirm.getByRole("button", { name: "Manter a corrida" }).click();
    await expect(confirm).toHaveCount(0);
    expect(await sent(page)).toEqual([]);

    await detail.locator("[data-ride-cancel]").click();
    await detail.getByRole("button", { name: "Cancelar a corrida A", exact: true }).click();
    await expect(detail.locator("[data-ride-cancel-state]")).toContainText(
      "Pedido de cancelamento enviado. Esperando a TaOn confirmar.",
    );
    await expect(detail.locator("[data-ride-cancel]")).toHaveCount(0);
    expect(await sent(page)).toEqual([{ key: "776753301", reason_id: null }]);
  });

  test("depois do aceite: o motivo é o próprio botão e vai como reason_id", async ({ page }) => {
    await page.goto("/deliveries?ride=776753302");
    const detail = page.locator("[data-ride-detail]");
    await detail.locator("[data-ride-cancel]").click();
    const confirm = detail.locator("[data-courier-cancel-confirm]");
    await expect(confirm).toContainText("Por que cancelar a corrida B?");
    await expect(confirm).toContainText("B07 volta para Aguardando.");
    await expect(confirm.locator("[data-courier-cancel-reason]")).toHaveText([
      "O entregador não está vindo",
      "Está demorando demais",
      "Não consegui falar com o entregador",
    ]);
    expect(await sent(page)).toEqual([]);
    await confirm.getByRole("button", { name: "Está demorando demais" }).click();
    await expect(detail.locator("[data-ride-cancel-state]")).toBeVisible();
    expect(await sent(page)).toEqual([{ key: "776753302", reason_id: 37 }]);
  });

  test("cancelamento pendente e recusa da TaOn aparecem na lista e no detalhe", async ({ page }) => {
    await page.goto("/deliveries");
    const mirrors = page.locator("[data-ride-mirror]");
    await expect(mirrors.nth(2).locator("[data-ride-mirror-cancel]")).toHaveText(
      "Pedido de cancelamento enviado. Esperando a TaOn confirmar.",
    );
    await expect(mirrors.nth(3).locator("[data-ride-mirror-cancel]")).toHaveText(
      "A TaOn não cancelou a corrida D. Cancele pela central da TaOn.",
    );
    await mirrors.nth(3).click();
    const detail = page.locator("[data-ride-detail]");
    await expect(detail.locator("[data-ride-cancel-state]")).toContainText("A TaOn não cancelou a corrida D.");
    // A corrida segue aberta na TaOn: o cancelar continua à mão.
    await expect(detail.locator("[data-ride-cancel]")).toBeVisible();
  });
});

test.describe("Painel do pedido: cancelar a corrida", () => {
  test("um toque arma a mesma confirmação; depois do aceite, o motivo vai junto", async ({ page }) => {
    await page.goto("/WEB-261116-B07");
    await page.locator("[data-courier-cancel]").click();
    expect(await sent(page)).toEqual([]);
    const confirm = page.locator("[data-courier-cancel-confirm]");
    await expect(confirm).toContainText("Por que cancelar a corrida B?");
    await confirm.getByRole("button", { name: "O entregador não está vindo" }).click();
    await expect(page.locator("[data-courier-cancel-state]")).toContainText(
      "Pedido de cancelamento enviado. Esperando a TaOn confirmar.",
    );
    await expect(page.locator("[data-courier-cancel]")).toHaveCount(0);
    expect(await sent(page)).toEqual([{ key: "776753302", reason_id: 12 }]);
  });

  test("a recusa da TaOn aparece no pedido, sem se passar por falha de abrir a corrida", async ({ page }) => {
    await page.goto("/WEB-261116-E02");
    await expect(page.locator("[data-courier-cancel-state]")).toContainText(
      "A TaOn não cancelou a corrida D. Cancele pela central da TaOn.",
    );
    await expect(page.getByText("Falha ao abrir a corrida")).toHaveCount(0);
  });
});
