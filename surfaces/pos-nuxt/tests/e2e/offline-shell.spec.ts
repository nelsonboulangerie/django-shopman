import { expect, test, type Page } from "@playwright/test";

// A VENDA ABRE SEM CONEXÃO (WP-PDV-SEM-CONEXAO §8). Antes, recarregar o PDV com a rede
// caída abria o `offline.html` e a venda parava, embora a fila em IndexedDB estivesse
// de pé. Agora a navegação da venda (`/`) vai à rede primeiro e, sem rede, abre o
// último HTML que a rede devolveu a este dispositivo (`offlineShellPaths` do kit).
// Ponta a ponta contra o build de produção (o service worker só existe nele) e o mock
// do balcão (cookie `pos_e2e=offline-sale`, ver `mockBackend.mjs`).
const saleMockPort = Number(process.env.POS_E2E_MOCK_PORT || 8798) + 1;
const SHOTS = process.env.POS_OFFLINE_SHOTS || "";

async function closesSeen(): Promise<Array<Record<string, unknown>>> {
  const answer = await fetch(`http://127.0.0.1:${saleMockPort}/__mock/closes`);
  return ((await answer.json()) as { closes: Array<Record<string, unknown>> }).closes;
}

/** O que o casco guardou: os caminhos no cache de runtime do PDV. */
async function shellPaths(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const cache = await caches.open("pos-shell");
    return (await cache.keys()).map((request) => new URL(request.url).pathname);
  });
}

/** Instala o service worker e deixa a venda guardada no casco, com a rede de pé. */
async function primeShell(page: Page) {
  await page.goto("/");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  // O worker não toma a aba que o instalou (`clientsClaim: false`): a navegação
  // seguinte já passa por ele, e é ela que guarda o casco.
  await page.reload();
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  await expect.poll(() => shellPaths(page)).toEqual(["/"]);
}

test.describe("PDV — a venda abre sem conexão", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await context.addCookies([{ name: "pos_e2e", value: "offline-sale", url: baseURL! }]);
  });

  test("recarregar com a rede caída abre a venda do dispositivo, e a venda guardada sobe na volta", async ({ page, context }) => {
    const before = (await closesSeen()).length;
    await primeShell(page);

    await context.setOffline(true);
    await page.reload();

    // A tela de venda, não o aviso de queda.
    await expect(page.locator("[data-pos-sale-screen]")).toBeVisible();
    await expect(page.getByText("O caixa ficou sem conexão")).toHaveCount(0);
    await expect(page.locator("[data-operator-offline-band]")).toContainText("Sem conexão");
    await expect(page.getByText("O balcão continua vendendo.", { exact: true })).toBeVisible();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/pdvoff-reload-${page.viewportSize()?.width}.png` });

    // A comanda livre abre só na tela (§3.4) e a venda em dinheiro vai para a fila.
    await page.getByText("#15", { exact: true }).last().click();
    await page.getByRole("button", { name: /Croissant R\$ 11,50/ }).first().click();
    await page.getByRole("button", { name: /Pagamento/ }).click();
    await expect(page.getByText(/^Total pelos preços das \d\d:\d\d/)).toBeVisible();
    await page.locator('[data-payment-method="cash"]').click();
    await page.getByRole("button", { name: "Validar" }).click();
    await expect(page.locator("[data-sale-result-offline]")).toBeVisible();
    await expect(page.getByText("1 venda esperando envio.", { exact: true })).toBeVisible();
    expect((await closesSeen()).length).toBe(before);

    await context.setOffline(false);
    await expect(page.getByText(/Venda guardada enviada: pedido NB-\d+\./)).toBeVisible({ timeout: 15_000 });
    const closes = await closesSeen();
    expect(closes.length).toBe(before + 1);
    expect(closes.at(-1)!.offline_captured_at).toBeTruthy();
    expect(closes.at(-1)!.expected_total_q).toBe(1150);
  });

  test("a venda guardada antes do reload continua na fila depois de abrir sem rede", async ({ page, context }) => {
    const before = (await closesSeen()).length;
    await primeShell(page);

    await context.setOffline(true);
    await page.getByText("#16", { exact: true }).last().click();
    await page.getByRole("button", { name: /Croissant R\$ 11,50/ }).first().click();
    await page.getByRole("button", { name: /Pagamento/ }).click();
    await page.locator('[data-payment-method="cash"]').click();
    await page.getByRole("button", { name: "Validar" }).click();
    await expect(page.locator("[data-sale-result-offline]")).toBeVisible();

    // Recarrega AINDA sem rede: a tela volta e a fila também.
    await page.reload();
    await expect(page.locator("[data-pos-sale-screen]")).toBeVisible();
    await expect(page.getByText("1 venda esperando envio.", { exact: true })).toBeVisible();

    await context.setOffline(false);
    await expect(page.getByText(/Venda guardada enviada: pedido NB-\d+\./)).toBeVisible({ timeout: 15_000 });
    expect((await closesSeen()).length).toBe(before + 1);
  });

  test("fora da venda, sem rede, segue o aviso de queda", async ({ page, context }) => {
    await primeShell(page);
    await context.setOffline(true);
    await page.goto("/session").catch(() => {});
    await expect(page.getByText("O caixa ficou sem conexão")).toBeVisible();
  });
});
