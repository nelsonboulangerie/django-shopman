import { expect, test, type BrowserContext, type Page } from "@playwright/test";

// A VENDA SEM CONEXÃO (WP-PDV-SEM-CONEXAO), ponta a ponta contra o mock do balcão:
// a rede cai no meio da venda, a venda fecha guardada no dispositivo, e quando a
// conexão volta a fila envia sozinha o MESMO fechamento (mesma chave), com a hora
// em que o balcão cobrou. O cookie `pos_e2e=offline-sale` leva o tráfego ao mock
// do cenário da venda (ver `mockBackend.mjs`).
const saleMockPort = Number(process.env.POS_E2E_MOCK_PORT || 8798) + 1;
const SHOTS = process.env.POS_OFFLINE_SHOTS || "";

async function closesSeen(): Promise<Array<Record<string, unknown>>> {
  const answer = await fetch(`http://127.0.0.1:${saleMockPort}/__mock/closes`);
  return ((await answer.json()) as { closes: Array<Record<string, unknown>> }).closes;
}

async function openFreeTabWithCroissant(page: Page, context: BrowserContext, baseURL: string, tab: string) {
  await context.addCookies([{ name: "pos_e2e", value: "offline-sale", url: baseURL }]);
  await page.goto("/");
  await page.getByText(`#${tab}`, { exact: true }).last().click();
  await page.getByRole("button", { name: /Croissant R\$ 11,50/ }).first().click();
  await expect(page.getByRole("button", { name: /Pagamento/ })).toBeEnabled();
}

async function payCashAndValidate(page: Page) {
  await page.getByRole("button", { name: /Pagamento/ }).click();
  await page.locator('[data-payment-method="cash"]').click();
  await page.getByRole("button", { name: "Validar" }).click();
}

test.describe("PDV — venda sem conexão", () => {
  test("a rede cai no meio da venda: fecha guardada e envia sozinha na volta", async ({ page, context, baseURL }) => {
    const before = (await closesSeen()).length;
    await openFreeTabWithCroissant(page, context, baseURL!, "15");

    await context.setOffline(true);
    await expect(page.getByText("Sem conexão. O balcão continua vendendo.")).toBeVisible();

    await page.getByRole("button", { name: /Pagamento/ }).click();
    await expect(page.getByText(/Sem conexão: total pelos preços das \d\d:\d\d/)).toBeVisible();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/pdvoff-pagamento-${page.viewportSize()?.width}.png` });
    await page.locator('[data-payment-method="cash"]').click();
    await page.getByRole("button", { name: "Validar" }).click();

    await expect(page.locator("[data-sale-result-offline]")).toBeVisible();
    await expect(page.getByText("Sem conexão. 1 venda esperando envio.")).toBeVisible();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/pdvoff-guardada-${page.viewportSize()?.width}.png` });
    await page.getByRole("button", { name: "Ver vendas guardadas" }).click();
    await expect(page.locator('[data-pos-offline-sale="pending"]')).toHaveCount(1);
    if (SHOTS) await page.waitForTimeout(600);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/pdvoff-lista-${page.viewportSize()?.width}.png` });
    await page.keyboard.press("Escape");
    expect((await closesSeen()).length).toBe(before);

    await context.setOffline(false);
    await expect(page.getByText(/Venda guardada enviada: pedido NB-\d+\./)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/venda esperando envio/)).toHaveCount(0);
    await expect(page.locator("[data-sale-result-offline-sent]")).toContainText(/Enviada: pedido NB-\d+/);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/pdvoff-enviada-${page.viewportSize()?.width}.png` });

    const closes = await closesSeen();
    expect(closes.length).toBe(before + 1);
    const sent = closes.at(-1)!;
    expect(String(sent.client_request_id)).toMatch(/^pos:/);
    expect(sent.offline_captured_at).toBeTruthy();
    expect(sent.expected_total_q).toBe(1150);
  });

  test("a rede cai COM o fechamento em voo: a fila reenvia a mesma chave", async ({ page, context, baseURL }) => {
    const before = (await closesSeen()).length;
    await openFreeTabWithCroissant(page, context, baseURL!, "16");

    // O POST do fechamento sai e a conexão cai antes da resposta.
    await page.route("**/sale/close/**", async (route) => {
      await context.setOffline(true);
      await route.abort("internetdisconnected");
    }, { times: 1 });
    await payCashAndValidate(page);

    await expect(page.locator("[data-sale-result-offline]")).toBeVisible();
    await expect(page.getByText("Sem conexão. 1 venda esperando envio.")).toBeVisible();

    await context.setOffline(false);
    await expect(page.getByText(/Venda guardada enviada: pedido NB-\d+\./)).toBeVisible({ timeout: 15_000 });
    const closes = await closesSeen();
    expect(closes.length).toBe(before + 1);
    expect(closes.at(-1)!.offline_captured_at).toBeTruthy();
  });
});
