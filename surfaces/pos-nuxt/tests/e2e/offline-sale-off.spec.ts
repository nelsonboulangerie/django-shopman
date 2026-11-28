import { expect, test } from "@playwright/test";

// A VENDA SEM CONEXÃO DESLIGADA NA LOJA (dono, 03/11/2026): é o padrão até existir
// NFC-e em contingência (tpEmis 9). Sem rede, o balcão NÃO cobra nem guarda venda: o
// aviso do cabeçalho diz que a venda espera a rede, o Pagamento fica apagado com a
// razão escrita abaixo, e nada vai para a fila. O cookie `pos_offline_sale=off` faz o
// mock do balcão responder com a chave desligada (`tests/visual/mockBackend.mjs`).
const saleMockPort = Number(process.env.POS_E2E_MOCK_PORT || 8798) + 1;

async function closesSeen(): Promise<Array<Record<string, unknown>>> {
  const answer = await fetch(`http://127.0.0.1:${saleMockPort}/__mock/closes`);
  return ((await answer.json()) as { closes: Array<Record<string, unknown>> }).closes;
}

test.describe("PDV — venda sem conexão desligada na loja", () => {
  test("sem rede: avisa, apaga o Pagamento com a razão e não guarda nada", async ({ page, context, baseURL }) => {
    const before = (await closesSeen()).length;
    await context.addCookies([
      { name: "pos_e2e", value: "offline-sale", url: baseURL! },
      { name: "pos_offline_sale", value: "off", url: baseURL! },
    ]);
    await page.goto("/");
    await page.getByText("#17", { exact: true }).last().click();
    await page.getByRole("button", { name: /Croissant R\$ 11,50/ }).first().click();
    const pay = page.getByRole("button", { name: /Pagamento/ });
    await expect(pay).toBeEnabled();

    await context.setOffline(true);
    await expect(page.getByText("Sem conexão: a venda espera a rede voltar.", { exact: true })).toBeVisible();
    await expect(page.getByText("O balcão continua vendendo.", { exact: true })).toHaveCount(0);
    await expect(pay).toBeDisabled();
    await expect(page.locator("[data-pos-sale-blocked-reason]").first()).toHaveText("Sem conexão. A venda espera a rede voltar.");

    // O F4 também não abre o Pagamento.
    await page.keyboard.press("F4");
    await expect(page.locator('[data-payment-method="cash"]')).toHaveCount(0);

    // A rede volta: a venda segue com conexão, e nada foi guardado no caminho.
    await context.setOffline(false);
    await expect(pay).toBeEnabled({ timeout: 15_000 });
    await expect(page.locator("[data-pos-sale-blocked-reason]")).toHaveCount(0);
    expect((await closesSeen()).length).toBe(before);
    await expect(page.getByText(/venda esperando envio/)).toHaveCount(0);
  });
});
