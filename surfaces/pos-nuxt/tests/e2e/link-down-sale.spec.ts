import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";

// O LINK CAI COM O WI-FI DE PÉ (laudo de go-live, U1/U2): o navegador continua
// dizendo `navigator.onLine === true`, e o que some é a resposta do servidor.
// Este spec NÃO usa `context.setOffline`: corta só a rota da API no navegador,
// com o fechamento em voo, e prova que o balcão segue vendendo. A venda que caiu
// no meio vai para a fila com a MESMA chave, a próxima já nasce guardada, e a
// volta do link (a sonda leve do kit) envia as duas sozinha.
const saleMockPort = Number(process.env.POS_E2E_MOCK_PORT || 8798) + 1;
const SHOTS = process.env.POS_LINK_SHOTS || "";
const API = "**/api/v1/**";

async function closesSeen(): Promise<Array<Record<string, unknown>>> {
  const answer = await fetch(`http://127.0.0.1:${saleMockPort}/__mock/closes`);
  return ((await answer.json()) as { closes: Array<Record<string, unknown>> }).closes;
}

async function openFreeTabWithCroissant(page: Page, tab: string) {
  await page.getByText(`#${tab}`, { exact: true }).last().click();
  await page.getByRole("button", { name: /Croissant R\$ 11,50/ }).first().click();
  await expect(page.getByRole("button", { name: /Pagamento/ })).toBeEnabled();
}

async function payCashAndValidate(page: Page) {
  await page.getByRole("button", { name: /Pagamento/ }).click();
  await page.locator('[data-payment-method="cash"]').click();
  await page.getByRole("button", { name: "Validar" }).click();
}

/** Corta a API quando o PRIMEIRO fechamento sai, e guarda a chave dele. */
async function cutApiAtClose(context: BrowserContext) {
  const state = { cut: false, abortedCloseKey: "" };
  await context.route(API, async (route: Route) => {
    const url = route.request().url();
    if (!state.cut && url.includes("/sale/close/")) {
      state.cut = true;
      state.abortedCloseKey = String(route.request().postDataJSON()?.client_request_id || "");
    }
    if (state.cut) return route.abort("connectionrefused");
    return route.continue();
  });
  return state;
}

test.describe("PDV — link caído com o wi-fi de pé", () => {
  test("o fechamento perde a resposta: o balcão segue vendendo e a fila envia a mesma chave", async ({ page, context, baseURL }) => {
    test.setTimeout(90_000);
    const before = (await closesSeen()).length;
    await context.addCookies([{ name: "pos_e2e", value: "offline-sale", url: baseURL! }]);
    await page.goto("/");
    const link = await cutApiAtClose(context);

    // 1ª venda: o POST do fechamento sai e não volta resposta nenhuma.
    await openFreeTabWithCroissant(page, "17");
    await payCashAndValidate(page);

    expect(await page.evaluate(() => navigator.onLine)).toBe(true);
    await expect(page.locator("[data-sale-result-offline]")).toBeVisible();
    await expect(page.getByText("1 venda esperando envio.", { exact: true })).toBeVisible();
    // A faixa do kit diz "Sem conexão" com o wi-fi de pé, e nenhum aviso de
    // resultado incerto trava o balcão.
    await expect(page.locator("[data-operator-offline-band]")).toContainText("Sem conexão");
    await expect(page.getByText("Resultado da cobrança não confirmado")).toHaveCount(0);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/t7-link-guardada-${page.viewportSize()?.width}.png` });

    // 2ª venda, ainda sem link: nasce guardada, sem esperar prazo nenhum.
    await page.keyboard.press("F2");
    await openFreeTabWithCroissant(page, "18");
    await payCashAndValidate(page);
    await expect(page.locator("[data-sale-result-offline]")).toBeVisible();
    await expect(page.getByText("2 vendas esperando envio.", { exact: true })).toBeVisible();
    expect((await closesSeen()).length).toBe(before);

    // O link volta: a sonda percebe e a fila envia as duas, sozinha.
    await context.unroute(API);
    await expect(page.getByText(/2 vendas guardadas enviadas: pedidos NB-\d+, NB-\d+\./)).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("[data-operator-offline-band]")).toHaveCount(0);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/t7-link-enviadas-${page.viewportSize()?.width}.png` });

    const closes = (await closesSeen()).slice(before);
    expect(closes).toHaveLength(2);
    // A venda que caiu no meio subiu com a MESMA chave do POST que perdeu a resposta.
    expect(link.abortedCloseKey).toMatch(/^pos:/);
    expect(closes.map((row) => row.client_request_id)).toContain(link.abortedCloseKey);
    for (const row of closes) {
      expect(row.offline_captured_at).toBeTruthy();
      expect(row.expected_total_q).toBe(1150);
    }
  });

  test("o Pix perde a resposta: Conferir agora reenvia a mesma venda e resolve sem cobrar de novo", async ({ page, context, baseURL }) => {
    test.setTimeout(90_000);
    const before = (await closesSeen()).length;
    await context.addCookies([{ name: "pos_e2e", value: "offline-sale", url: baseURL! }]);
    await page.goto("/");

    // O servidor RECEBE o fechamento e fecha; a resposta é que se perde no caminho.
    let lost = false;
    await context.route("**/sale/close/**", async (route) => {
      if (lost) return route.continue();
      lost = true;
      await route.fetch();
      return route.abort("connectionreset");
    });
    await openFreeTabWithCroissant(page, "17");
    await page.getByRole("button", { name: /Pagamento/ }).click();
    await page.locator('[data-payment-method="pix"]').click();
    await page.getByRole("button", { name: "Validar" }).click();

    // Pix não espera na fila: a venda trava, e a saída é Conferir agora.
    const notice = page.getByText("A venda ficou sem resposta. Conferir agora pergunta por esta mesma venda, sem cobrar de novo.");
    await expect(notice).toBeVisible();
    for (const scheme of SHOTS ? (["light", "dark"] as const) : []) {
      // O PDV é claro por escolha (colorMode `light`): o escuro é a classe do toggle.
      await page.evaluate((dark) => document.documentElement.classList.toggle("dark", dark), scheme === "dark");
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${SHOTS}/t7-conferir-agora-depois-${scheme}.png` });
    }
    const recheck = page.getByRole("button", { name: "Conferir agora" });
    if (await recheck.isVisible()) await recheck.click();

    // Resolveu (pelo toque ou pela volta da sonda): a trava some e a venda aparece.
    await expect(notice).toHaveCount(0, { timeout: 15_000 });
    const closes = (await closesSeen()).slice(before);
    expect(closes.length).toBe(2);
    expect(closes[1]!.client_request_id).toBe(closes[0]!.client_request_id);
    expect(closes[1]).toEqual(closes[0]);
  });

  test("captura do aviso antigo (trava sem o corpo guardado)", async ({ page, context, baseURL }) => {
    test.skip(!SHOTS, "só para as capturas do antes");
    await context.addCookies([{ name: "pos_e2e", value: "offline-sale", url: baseURL! }]);
    await page.addInitScript(() => {
      localStorage.setItem("shopman:pos:close-outcome-uncertain", JSON.stringify({
        client_request_id: "pos:captura", owner_id: "x", state: "uncertain", recorded_at: new Date().toISOString(),
      }));
    });
    await page.goto("/");
    await expect(page.getByText("Resultado da cobrança não confirmado").first()).toBeVisible();
    for (const scheme of ["light", "dark"] as const) {
      // O PDV é claro por escolha (colorMode `light`): o escuro é a classe do toggle.
      await page.evaluate((dark) => document.documentElement.classList.toggle("dark", dark), scheme === "dark");
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${SHOTS}/t7-conferir-agora-antes-${scheme}.png` });
    }
  });
});
