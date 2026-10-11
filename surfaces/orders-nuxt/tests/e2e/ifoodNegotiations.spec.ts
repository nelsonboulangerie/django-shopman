import { test, expect } from "@playwright/test";

for (const width of [375, 820, 1280]) {
  test(`negociação após entrega exige decisão explícita — ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const actions = ["accept", "reject"].map(decision => ({ ref: decision, label: decision, enabled: true, reason: "", method: "POST", payload_schema: { expected_actor_id: 1, base_revision: "r1", dispute_id: "dispute-1", decision }, confirmation: { description: decision === "accept" ? "Aceitar autoriza o cancelamento deste pedido conforme a solicitação do cliente." : "Recusar envia sua decisão para o iFood." } }));
    const dispute = { id: "dispute-1", type: "AFTER_DELIVERY", action: "CANCELLATION", message: "O cliente informa que faltou o café. Confira os itens antes de responder.", expires_at: "2030-09-15T18:15:00Z", timeout_action: "REJECT_CANCELLATION", state: "open", can_respond: true, response_notice: "", items: ["1× Café com leite"], evidence_urls: [], accept_reasons: ["PRODUCT_QUALITY", "CUSTOMER_SATISFACTION"], reject_reasons: ["WRONG_ORDER", "CUSTOMER_REQUEST"], alternatives_available: true, actions };
    let card: Record<string, unknown> = {};
    await page.route("**/api/v1/backstage/orders/", async route => {
      const response = await route.fetch();
      const body = await response.json();
      card = { ...body.queue.prep[0], ref: "IFOOD-COMPLETED", channel_ref: "ifood", status: "completed", status_label: "Concluído", customer_name: "Cliente de teste", ifood_negotiations: [dispute], actions: [], can_advance: false, can_confirm: false, attention: "negotiation", attention_since_iso: new Date().toISOString(), goal_minutes: 10, goal_label: "responder até 15:15" };
      body.queue.ifood_negotiation_orders = [card];
      await route.fulfill({ json: body });
    });
    await page.route("**/api/v1/backstage/orders/IFOOD-COMPLETED/", route => route.fulfill({ json: { order: {
      ...card, customer_phone: "", customer_phone_uri: "", customer_whatsapp_url: "", customer_email: "", customer_ref: "", delivery_address: "", delivery_instructions: "", items: [{ sku: "CAFE", name: "Café com leite", qty: "1", unit_price_display: "R$ 10,00", total_display: "R$ 10,00" }], timeline: [], kitchen_note: "", customer_note: "", fiscal_links: [], awaiting_work_orders: [], equipment_options: [], equipment_out: [], cancellation_presets: [], kitchen_note_tags: [], customer_profile: null, revisions: {},
    } } }));
    await page.goto("/");
    if (width >= 1024) {
      // A negociação entra no "Precisa de você" como os outros pedidos (dono, 07/10/2026).
      const row = page.locator('[data-queue-ref="IFOOD-COMPLETED"]');
      await expect(row).toBeVisible();
      await expect(row.locator("[data-queue-negotiation]")).toBeVisible();
      await row.getByRole("link", { name: "Responder" }).click();
    } else {
      // A Fila é do desktop. No celular e no tablet em pé o quadro é em abas, e o pedido
      // já entregue com negociação aberta não está em etapa nenhuma: ele ganha a aba
      // "Negociação", com a contagem, e o cartão leva à solicitação.
      const tabs = page.locator("[data-board-zone-tabs]");
      await expect(tabs).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`board-${width}.png`) });
      const tab = tabs.getByRole("tab", { name: /Negociação/ });
      await expect(tab).toBeVisible();
      await expect(tab.locator("[data-count-chip]")).toHaveText("1");
      // As quatro abas cabem na largura: nenhuma fica cortada na borda.
      expect(await tabs.locator('[role="tablist"]').evaluate((list) => list.scrollWidth <= list.clientWidth)).toBe(true);
      await tab.click();
      await expect(tab).toHaveAttribute("aria-selected", "true");
      const column = page.locator('[data-zone="negotiation"]');
      await expect(column.getByText("Cliente de teste")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      // O traço da aba ativa desliza até ela: a captura espera a transição.
      await page.waitForTimeout(400);
      await page.screenshot({ path: testInfo.outputPath(`board-negotiation-${width}.png`) });
      // O aviso do cartão é a pílula "Negociação iFood"; o toque abre a ação.
      await column.locator('[data-card-notice="negotiation"]').click();
      await page.locator("[data-ifood-negotiation-link]").click();
    }
    const form = page.locator("[data-ifood-negotiations]");
    await expect(form).toBeVisible();
    await expect(form.getByRole("button", { name: "Enviar resposta ao iFood" })).toBeDisabled();
    await form.getByRole("combobox", { name: "Decisão", exact: true }).click();
    await page.getByRole("option", { name: "Aceitar solicitação", exact: true }).click();
    await form.getByRole("combobox", { name: "Motivo informado pelo iFood", exact: true }).click();
    await page.getByRole("option", { name: "Qualidade do produto", exact: true }).click();
    await expect(form.getByRole("button", { name: "Enviar resposta ao iFood" })).toBeDisabled();
    await form.getByRole("checkbox").check();
    await expect(form.getByRole("button", { name: "Enviar resposta ao iFood" })).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await form.screenshot({ path: testInfo.outputPath(`negotiation-${width}.png`) });
  });
}
