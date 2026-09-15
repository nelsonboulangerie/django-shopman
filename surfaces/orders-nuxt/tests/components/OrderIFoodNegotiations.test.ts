import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import OrderIFoodNegotiations from "../../app/components/OrderIFoodNegotiations.vue";
import type { Action, IFoodNegotiationProjection } from "../../app/generated/ordersContract";
const executePath = vi.fn();
vi.stubGlobal("useOrderIntention", () => ({ executePath }));
vi.stubGlobal("httpError", (error: { data?: unknown }) => ({ status: 0, data: error.data }));
function action(ref: string): Action {
  return { ref, label: ref, enabled: true, reason: "", method: "POST", payload_schema: { expected_actor_id: 7, base_revision: "r1", dispute_id: "dispute-1", decision: ref }, confirmation: { description: ref === "accept" ? "Aceitar cancela este pedido conforme a solicitação." : "Recusar envia a decisão ao iFood." } } as Action;
}
function negotiation(over: Partial<IFoodNegotiationProjection> = {}): IFoodNegotiationProjection {
  return { id: "dispute-1", type: "AFTER_DELIVERY", action: "CANCELLATION", message: "Faltou o café.", expires_at: "2030-09-15T18:15:00Z", timeout_action: "ACCEPT_CANCELLATION", state: "open", can_respond: true, response_notice: "", items: ["1× Café"], evidence_urls: [], accept_reasons: ["PRODUCT_QUALITY"], reject_reasons: ["ORDER_DELIVERED"], alternatives_available: false, actions: [action("accept"), action("reject")], ...over };
}
function render(item = negotiation()) { return mount(OrderIFoodNegotiations, { props: { orderRef: "IFOOD-123", negotiations: [item] } }); }
beforeEach(() => { executePath.mockReset(); executePath.mockResolvedValue({ outcome: "applied" }); });
describe("OrderIFoodNegotiations", () => {
  it("requires explicit decision, dynamic reason and consequence confirmation", async () => {
    const w = render();
    expect((w.get("select").element as HTMLSelectElement).value).toBe("");
    expect(w.get('button[type="submit"]').attributes("disabled")).toBeDefined();
    await w.get("select").setValue("accept");
    expect(w.text()).toContain("Aceitar cancela este pedido");
    expect(w.text()).toContain("Qualidade do produto");
    expect(w.get("textarea").attributes("maxlength")).toBe("250");
    await w.findAll("select")[1]!.setValue("PRODUCT_QUALITY");
    await w.get("textarea").setValue(" Café não recebido. ");
    expect(w.get('button[type="submit"]').attributes("disabled")).toBeDefined();
    await w.get('input[type="checkbox"]').setValue(true);
    await w.get("form").trigger("submit"); await flushPromises();
    expect(executePath).toHaveBeenCalledWith("IFOOD-123:ifood-handshake:dispute-1", "/api/v1/backstage/orders/IFOOD-123/ifood-handshake/", expect.objectContaining({ ref: "accept", payload_schema: expect.objectContaining({ base_revision: "r1", decision: "accept" }) }), { reason: "PRODUCT_QUALITY", detail_reason: "Café não recebido." });
    expect(w.emitted("refresh")).toHaveLength(1);
    expect(w.text()).toContain("Aguarde a confirmação do iFood");
    expect(w.find("form").exists()).toBe(false);
  });
  it("requires rejection reason and clears acceptance details when switching", async () => {
    const w = render(); await w.get("select").setValue("accept"); await w.get("textarea").setValue("rascunho");
    await w.get("select").setValue("reject"); expect(w.find("textarea").exists()).toBe(false);
    expect(w.text()).not.toContain("PRODUCT_QUALITY");
    await w.get('input[type="checkbox"]').setValue(true);
    expect(w.get('button[type="submit"]').attributes("disabled")).toBeDefined();
    await w.findAll("select")[1]!.setValue("ORDER_DELIVERED"); await w.get('input[type="checkbox"]').setValue(true);
    await w.get("form").trigger("submit"); await flushPromises();
    expect(executePath.mock.calls[0]?.[3]).toEqual({ reason: "ORDER_DELIVERED", detail_reason: "" });
  });
  it("allows acceptance without reason only with no supplied reasons", async () => {
    const w = render(negotiation({ accept_reasons: [] })); await w.get("select").setValue("accept"); await w.get('input[type="checkbox"]').setValue(true);
    expect(w.findAll("select")).toHaveLength(1); expect(w.get('button[type="submit"]').attributes("disabled")).toBeUndefined();
  });
  it("blocks changed revision and read-only/expired negotiations", async () => {
    const w = render(); await w.get("select").setValue("accept"); await w.findAll("select")[1]!.setValue("PRODUCT_QUALITY"); await w.get('input[type="checkbox"]').setValue(true);
    await w.setProps({ negotiations: [negotiation({ actions: [{ ...action("accept"), payload_schema: { ...action("accept").payload_schema, base_revision: "r2" } }, action("reject")] })] });
    expect(w.text()).toContain("A negociação foi atualizada"); expect(w.get('button[type="submit"]').attributes("disabled")).toBeDefined();
    await w.setProps({ negotiations: [negotiation({ can_respond: false, response_notice: "Prazo encerrado." })] });
    expect(w.find("form").exists()).toBe(false); expect(w.text()).toContain("Prazo encerrado."); expect(executePath).not.toHaveBeenCalled();
  });
  it("freezes an uncertain response and retries exactly the same intention", async () => {
    executePath.mockRejectedValueOnce(new Error("network")); const w = render(negotiation({ accept_reasons: [] }));
    await w.get("select").setValue("accept"); await w.get('input[type="checkbox"]').setValue(true); await w.get("form").trigger("submit"); await flushPromises();
    expect(w.get("fieldset").attributes("disabled")).toBeDefined(); expect(w.text()).toContain("Verificar mesmo envio");
    await w.get('button[type="button"]').trigger("click"); await flushPromises(); expect(executePath.mock.calls[1]).toEqual(executePath.mock.calls[0]);
  });
  it("releases a definitively refused intention for review", async () => {
    executePath.mockRejectedValueOnce({ data: { outcome: "not_applied" } });
    const w = render(negotiation({ accept_reasons: [] }));
    await w.get("select").setValue("accept"); await w.get('input[type="checkbox"]').setValue(true); await w.get("form").trigger("submit"); await flushPromises();
    expect(w.get("fieldset").attributes("disabled")).toBeUndefined();
    expect(w.text()).toContain("A resposta não foi aplicada");
    expect((w.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false);
  });
  it("permits only the current order's evidence proxy among relative URLs", () => {
    const good = "/api/v1/backstage/orders/IFOOD-123/ifood-handshake-evidence/?dispute_id=dispute-1&index=0";
    const w = render(negotiation({ evidence_urls: [good, "//evil.example/test", "/arbitrary", "/api/v1/backstage/orders/OTHER/ifood-handshake-evidence/?index=0"] }));
    expect(w.findAll("a")).toHaveLength(1); expect(w.get("a").attributes("href")).toBe(good);
  });
  it("only links HTTPS evidence, escapes content and explains unsupported alternatives", () => {
    const w = render(negotiation({ evidence_urls: ["javascript:alert(1)", "http://example.com/a", "https://example.com/evidence"], message: "<img src=x onerror=alert(1)>", alternatives_available: true, timeout_action: "UNKNOWN" }));
    expect(w.findAll("a")).toHaveLength(1); expect(w.get("a").attributes("rel")).toBe("noopener noreferrer"); expect(w.find("img").exists()).toBe(false);
    expect(w.text()).toContain("use o canal do iFood"); expect(w.text()).toContain("consequência do vencimento não foi informada");
  });
});
