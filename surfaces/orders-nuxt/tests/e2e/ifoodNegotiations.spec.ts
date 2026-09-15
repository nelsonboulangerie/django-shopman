import { test, expect } from "@playwright/test";

for (const width of [375, 1280]) {
  test(`negociação após entrega exige decisão explícita — ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const actions = ["accept", "reject"].map(decision => ({ ref: decision, label: decision, enabled: true, reason: "", method: "POST", payload_schema: { expected_actor_id: 1, base_revision: "r1", dispute_id: "dispute-1", decision }, confirmation: { description: decision === "accept" ? "Aceitar autoriza o cancelamento deste pedido conforme a solicitação do cliente." : "Recusar envia sua decisão para o iFood." } }));
    const dispute = { id: "dispute-1", type: "AFTER_DELIVERY", action: "CANCELLATION", message: "O cliente informa que faltou o café. Confira os itens antes de responder.", expires_at: "2030-09-15T18:15:00Z", timeout_action: "REJECT_CANCELLATION", state: "open", can_respond: true, response_notice: "", items: ["1× Café com leite"], evidence_urls: [], accept_reasons: ["PRODUCT_QUALITY", "CUSTOMER_SATISFACTION"], reject_reasons: ["WRONG_ORDER", "CUSTOMER_REQUEST"], alternatives_available: true, actions };
    let card: Record<string, unknown> = {};
    await page.route("**/api/v1/backstage/orders/", async route => {
      const response = await route.fetch();
      const body = await response.json();
      card = { ...body.queue.prep[0], ref: "IFOOD-COMPLETED", channel_ref: "ifood", status: "completed", status_label: "Concluído", customer_name: "Cliente de teste", ifood_negotiations: [dispute], actions: [], can_advance: false, can_confirm: false };
      body.queue.ifood_negotiation_orders = [card];
      await route.fulfill({ json: body });
    });
    await page.route("**/api/v1/backstage/orders/IFOOD-COMPLETED/", route => route.fulfill({ json: { order: {
      ...card, customer_phone: "", customer_phone_uri: "", customer_whatsapp_url: "", customer_email: "", customer_ref: "", delivery_address: "", delivery_instructions: "", items: [{ sku: "CAFE", name: "Café com leite", qty: "1", unit_price_display: "R$ 10,00", total_display: "R$ 10,00" }], timeline: [], kitchen_note: "", customer_note: "", fiscal_links: [], awaiting_work_orders: [], equipment_options: [], equipment_out: [], cancellation_presets: [], kitchen_note_tags: [], customer_profile: null, revisions: {},
    } } }));
    await page.goto("/");
    await page.getByRole("button", { name: "Atualizar (atalho: r)" }).click();
    const section = page.locator("[data-ifood-negotiation-orders]");
    await expect(section).toBeVisible();
    await expect(section.getByRole("button", { name: "Selecionar pedido" })).toHaveCount(0);
    await section.locator("[data-ifood-negotiation-link]").click();
    const form = page.locator("[data-ifood-negotiations]");
    await expect(form).toBeVisible();
    await expect(form.getByRole("button", { name: "Enviar resposta ao iFood" })).toBeDisabled();
    await form.getByRole("combobox", { name: "Decisão", exact: true }).selectOption("accept");
    await form.getByRole("combobox", { name: "Motivo informado pelo iFood", exact: true }).selectOption("PRODUCT_QUALITY");
    await expect(form.getByRole("button", { name: "Enviar resposta ao iFood" })).toBeDisabled();
    await form.locator('input[type="checkbox"]').check();
    await expect(form.getByRole("button", { name: "Enviar resposta ao iFood" })).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await form.screenshot({ path: testInfo.outputPath(`negotiation-${width}.png`) });
  });
}
