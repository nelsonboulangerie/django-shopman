import { ref } from "vue";
import { fixtureActions } from "../support/orderActions";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOrderDetail } from "../../app/composables/useOrderDetail";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { id: 1 } }) }));

describe("useOrderDetail", () => {
  beforeEach(() => {
    env.reset();
    const actions = fixtureActions({ can_confirm: true });
    env.fetchData.value = { order: { actions: [...actions, { ...actions[1]!, ref: "cancel" }, { ...actions[1]!, ref: "resend-payment-link" }] } };
    env.fetchMock.mockResolvedValue({ outcome: "applied" });
  });

  it("deriva order da projection; null quando vazio", () => {
    env.fetchData.value = { order: { ref: "WEB-1", status: "accepted" } };
    expect(useOrderDetail("WEB-1").order.value).toEqual({ ref: "WEB-1", status: "accepted" });
    env.fetchData.value = null;
    expect(useOrderDetail("WEB-1").order.value).toBeNull();
  });

  it("confirm posta em /orders/{ref}/confirm/ e reconcilia via refresh", async () => {
    env.fetchData.value = { order: { ref: "WEB-1", actions: fixtureActions({ can_confirm: true }) } };
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    const d = useOrderDetail("WEB-1");
    expect(await d.confirm()).toBe(true);
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/WEB-1/confirm/");
    expect(env.refresh).toHaveBeenCalledTimes(1);
  });

  it("reject/cancel enviam reason + cancellation_code (vazio p/ canal não-marketplace)", async () => {
    const d = useOrderDetail("WEB-2");
    await d.reject("sem estoque");
    expect(env.fetchMock.mock.calls[0]![1].body).toMatchObject({ reason: "sem estoque", cancellation_code: "" });
    await d.cancel("cliente desistiu");
    expect(env.fetchMock.mock.calls[1]![1].body).toMatchObject({ reason: "cliente desistiu", cancellation_code: "" });
  });

  it("reject/cancel de iFood repassam o código exigido pelo marketplace", async () => {
    const d = useOrderDetail("IFOOD-2");
    await d.reject("Item em falta", "IN_STORE_OUT_OF_STOCK");
    expect(env.fetchMock.mock.calls[0]![1].body).toMatchObject({ reason: "Item em falta", cancellation_code: "IN_STORE_OUT_OF_STOCK" });
    await d.cancel("Loja fechada", "STORE_CLOSED");
    expect(env.fetchMock.mock.calls[1]![1].body).toMatchObject({ reason: "Loja fechada", cancellation_code: "STORE_CLOSED" });
  });

  it("fetchCancellationReasons devolve a lista do pedido, propaga indisponibilidade", async () => {
    env.fetchMock.mockResolvedValueOnce({ reasons: [{ code: "1", description: "Sem estoque" }] });
    const d = useOrderDetail("IFOOD-3");
    expect(await d.fetchCancellationReasons()).toEqual([{ code: "1", description: "Sem estoque" }]);
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/IFOOD-3/cancellation-reasons/");
    env.fetchMock.mockRejectedValueOnce(new Error("boom"));
    await expect(d.fetchCancellationReasons()).rejects.toThrow("boom");
  });

  it("guarda de reentrância: 2ª ação enquanto em voo é no-op", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise((r) => { release = () => r({ outcome: "applied" }); }));
    env.fetchData.value = { order: { ref: "WEB-3", actions: fixtureActions({ can_advance: true }) } };
    const d = useOrderDetail("WEB-3");
    const first = d.advance();
    expect(d.busy.value).toBe(true);
    expect(await d.confirm()).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
    expect(d.busy.value).toBe(false);
  });

  it("falha → toast do detalhe do servidor + false", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Pagamento pendente" } });
    env.fetchData.value = { order: { ref: "WEB-4", actions: fixtureActions({ can_confirm: true }) } };
    const d = useOrderDetail("WEB-4");
    expect(await d.confirm()).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("Pagamento pendente");
  });

  it("resendPaymentLink posta em /orders/{ref}/resend-payment-link/ e tosta sucesso", async () => {
    const d = useOrderDetail("PDV-9");
    expect(await d.resendPaymentLink()).toBe(true);
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/PDV-9/resend-payment-link/");
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(env.sonner.success).toHaveBeenCalledWith("Reenvio do link solicitado.");
  });

  it("reenvio recusado pelo servidor → o motivo vira toast, sem sucesso", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 409, data: { detail: "O link venceu. Refaça a venda para gerar um novo.", error: { code: "payment_link_expired" } } });
    const d = useOrderDetail("PDV-10");
    expect(await d.resendPaymentLink()).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("O link venceu. Refaça a venda para gerar um novo.");
    expect(env.sonner.success).not.toHaveBeenCalled();
  });

  it("cancelamento de pedido pago abre o desafio do gerente em vez de tostar erro", async () => {
    // ⚠️ O servidor pede a segunda assinatura com um erro TIPADO
    // (`validate_manager_override` → `manager_approval_required`). O `act`
    // engolia qualquer erro num toast, então o gerente lia "Falha na ação" e
    // não tinha ONDE assinar — o pedido pago não cancelava pelo Gestor, e
    // nenhuma outra superfície cancela pedido da loja.
    env.fetchMock.mockRejectedValueOnce({
      status: 422,
      data: { detail: "Cancelar pedido pago exige autorização.", error: { code: "manager_approval_required" } },
    });
    const d = useOrderDetail("WEB-PAGO");

    expect(await d.cancel("cliente desistiu")).toBe(false);
    // Desafio NÃO é falha: um toast vermelho aqui ensina que o sistema quebrou.
    expect(env.sonner.error).not.toHaveBeenCalled();
    expect(d.managerChallenge.value?.code).toBe("manager_approval_required");
  });

  it("assinar reenvia o MESMO ato com a autorização, sem refazer o gesto", async () => {
    env.fetchMock.mockRejectedValueOnce({
      status: 422,
      data: { detail: "precisa de gerente", error: { code: "manager_approval_required" } },
    });
    const d = useOrderDetail("WEB-PAGO2");
    await d.cancel("cliente desistiu", "");

    expect(await d.authorize({ username: "joyce", pin: "1234" })).toBe(true);

    // O motivo escolhido sobrevive ao desafio — o gerente não redigita nada.
    const body = env.fetchMock.mock.calls[1]![1].body;
    expect(body.reason).toBe("cliente desistiu");
    expect(body.manager_approval).toEqual({ username: "joyce", pin: "1234" });
    expect(env.fetchMock.mock.calls[1]![1].headers["Idempotency-Key"]).toBe(env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"]);
    expect(d.managerChallenge.value).toBeNull();
  });

  it("saveNotes/addComment enviam o corpo e tostam sucesso", async () => {
    env.fetchData.value = { order: { actions: [{ ...fixtureActions({ can_advance: true })[0], ref: "notes", payload_schema: { base_revision: "note-base" } }, { ...fixtureActions({ can_advance: true })[0], ref: "comment", payload_schema: { base_revision: "comment-base" } }] } };
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    const d = useOrderDetail("WEB-5");
    await d.saveNotes("frágil");
    expect(env.fetchMock.mock.calls[0]![1].body).toEqual({ notes: "frágil", base_revision: "note-base" });
    expect(env.sonner.success).toHaveBeenCalledWith("Notas salvas.");
    await d.addComment("ligar antes");
    expect(env.fetchMock.mock.calls[1]![1].body).toEqual({ note: "ligar antes", base_revision: "comment-base" });
    expect(env.sonner.success).toHaveBeenCalledWith("Comentário adicionado.");
  });
});
