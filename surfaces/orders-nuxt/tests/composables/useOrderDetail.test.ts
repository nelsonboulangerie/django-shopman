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

  // A primeira chamada é o sheet único das Entregas (#2876); o detalhe guarda o
  // "Chamar de novo", pelo mesmo protocolo de intenção.
  it("chamar de novo com resposta perdida consulta recibo e informa somente fila", async () => {
    const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-dispatch-again" };
    env.fetchData.value = { order: { ref: "COURIER-LOST", actions: [action] } };
    env.fetchMock.mockRejectedValueOnce(new Error("response lost"));
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied", status: "queued", directive_id: 7 });
    expect(await useOrderDetail("COURIER-LOST").courierDispatchAgain()).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledTimes(2);
    const [url, options] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("COURIER-LOST/courier-dispatch-again/");
    expect(options.body.base_revision).toBe(action.payload_schema.base_revision);
    expect(options.headers["Idempotency-Key"]).toBeTruthy();
    expect((env.fetchMock.mock.calls[1]![1].method ?? "GET")).toBe("GET");
    expect(env.sonner.success).toHaveBeenCalledWith("Pedido de entregador enviado à TaOn.");
  });

  it("deriva order da projection; null quando vazio", () => {
    env.fetchData.value = { order: { ref: "WEB-1", status: "accepted" } };
    expect(useOrderDetail("WEB-1").order.value).toEqual({ ref: "WEB-1", status: "accepted" });
    env.fetchData.value = null;
    expect(useOrderDetail("WEB-1").order.value).toBeNull();
  });

  // WP-G05 (P1-20): três recusas liam a mesma frase. O composable diz qual foi.
  it("403 de permissão é `forbidden`; 404 é `notFound`; rede não é nenhum dos dois", () => {
    env.fetchData.value = null;
    env.fetchError.value = { statusCode: 403, data: { detail: "Você não tem permissão." } };
    const denied = useOrderDetail("WEB-403");
    expect([denied.forbidden.value, denied.notFound.value]).toEqual([true, false]);

    env.fetchError.value = { statusCode: 404, data: { detail: "Pedido não encontrado." } };
    const missing = useOrderDetail("WEB-404");
    expect([missing.forbidden.value, missing.notFound.value]).toEqual([false, true]);

    env.fetchError.value = { statusCode: 503 };
    const offline = useOrderDetail("WEB-503");
    expect([offline.forbidden.value, offline.notFound.value]).toEqual([false, false]);
  });

  it("estação travada e sessão caída não são falta de permissão", () => {
    env.fetchData.value = null;
    env.fetchError.value = { statusCode: 403, data: { error: { code: "station_locked" } } };
    expect(useOrderDetail("WEB-LOCK").forbidden.value).toBe(false);
    env.fetchError.value = { statusCode: 403, data: { error: { code: "not_authenticated" } } };
    expect(useOrderDetail("WEB-OUT").forbidden.value).toBe(false);
  });

  // WP-G05 (P1-14): a DANFE no detalhe é o MESMO gesto do cartão do painel.
  it("printDanfe pede a DANFE deste pedido ao servidor e relê o pedido", async () => {
    env.fetchData.value = { order: { ref: "DLV-7", actions: [] }, device_agent: { can_print: false, reason: "Sem agente." } };
    env.fetchMock.mockResolvedValueOnce({ via: "relay", reprint: false, target_label: "Balcão" });
    const d = useOrderDetail("DLV-7");

    expect(d.danfePrinting.value).toBe(false);
    expect(await d.printDanfe()).toBe(true);

    const [url, options] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/orders/DLV-7/danfe-escpos/");
    expect(options).toMatchObject({ method: "POST", body: { local_agent: false } });
    expect(env.sonner.success).toHaveBeenCalledWith("DANFE do pedido DLV-7 enviada para a impressora de Balcão.");
    expect(env.refresh).toHaveBeenCalled();
    expect(d.danfePrinting.value).toBe(false);
  });

  it("confirm posta em /orders/{ref}/confirm/ e reconcilia via refresh", async () => {
    env.fetchData.value = { order: { ref: "WEB-1", actions: fixtureActions({ can_confirm: true }) } };
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    const d = useOrderDetail("WEB-1");
    expect(await d.confirm()).toBe(true);
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/WEB-1/confirm/");
    expect(env.refresh).toHaveBeenCalledTimes(1);
  });

  it("recusar e cancelar enviam a CHAVE do motivo da lista única e a observação interna, em qualquer canal", async () => {
    const d = useOrderDetail("IFOOD-2");
    await d.reject({ reasonKey: "out_of_stock", internalNote: "faltou farinha" });
    expect(env.fetchMock.mock.calls[0]![1].body).toMatchObject({ reason_key: "out_of_stock", internal_note: "faltou farinha" });
    await d.cancel({ reasonKey: "customer_request", internalNote: "ligou às 10h" });
    expect(env.fetchMock.mock.calls[1]![1].body).toMatchObject({ reason_key: "customer_request", internal_note: "ligou às 10h" });
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

    expect(await d.cancel({ reasonKey: "customer_request", internalNote: "" })).toBe(false);
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
    await d.cancel({ reasonKey: "customer_request", internalNote: "ligou às 10h" });

    expect(await d.authorize({ username: "joyce", pin: "1234" })).toBe(true);

    // O motivo escolhido sobrevive ao desafio — o gerente não redigita nada.
    const body = env.fetchMock.mock.calls[1]![1].body;
    expect(body.reason_key).toBe("customer_request");
    expect(body.internal_note).toBe("ligou às 10h");
    expect(body.manager_approval).toEqual({ username: "joyce", pin: "1234" });
    expect(env.fetchMock.mock.calls[1]![1].headers["Idempotency-Key"]).toBe(env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"]);
    expect(d.managerChallenge.value).toBeNull();
  });

  it("devolução usa a ação da prévia, pede o gerente e reenvia os itens e o motivo com a assinatura", async () => {
    // WP-G12: a ação `return` não mora na projeção do detalhe; vem da prévia
    // (`return/preview/`), com a base que o comando confere.
    const contract = { ...fixtureActions({ can_confirm: true })[0]!, ref: "return", enabled: true, payload_schema: { base_revision: "return-base", expected_actor_id: 1 } };
    env.fetchMock.mockRejectedValueOnce({
      status: 422,
      data: { detail: "Devolução pede a autorização de um gerente.", error: { code: "manager_approval_required" } },
    });
    const d = useOrderDetail("WEB-DEV");
    const choice = { items: [{ line_id: "L1", qty: "2" }], reason: "Croissant cru" };

    expect(await d.returnOrder(choice, contract)).toBe(false);
    expect(d.managerChallenge.value).toMatchObject({ code: "manager_approval_required", action: "return" });
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/WEB-DEV/return/");
    expect(env.fetchMock.mock.calls[0]![1].body).toMatchObject({ base_revision: "return-base", items: choice.items, reason: "Croissant cru" });

    expect(await d.authorize({ username: "joyce", pin: "1234" })).toBe(true);
    const body = env.fetchMock.mock.calls[1]![1].body;
    expect(body.items).toEqual(choice.items);
    expect(body.manager_approval).toEqual({ username: "joyce", pin: "1234" });
    expect(d.managerChallenge.value).toBeNull();
  });

  it("não retirado usa a ação da prévia, pede o gerente e reenvia com a assinatura", async () => {
    // WP-G11: a ação `no-show` do detalhe só abre a porta (rótulo, se já pode); quem
    // leva a base que o comando confere é a da prévia (`no-show/preview/`).
    const base = fixtureActions({ can_confirm: true })[0]!;
    env.fetchData.value = { order: { ref: "WEB-NR", actions: [{ ...base, ref: "no-show", priority: "menu", payload_schema: { base_revision: "detail-base", expected_actor_id: 1 } }] } };
    const contract = { ...base, ref: "no-show", label: "Encerrar como não retirado", enabled: true, payload_schema: { base_revision: "no-show-base", expected_actor_id: 1 } };
    env.fetchMock.mockRejectedValueOnce({
      status: 422,
      data: { detail: "Não retirado pede a autorização de um gerente.", error: { code: "manager_approval_required" } },
    });
    const d = useOrderDetail("WEB-NR");

    expect(await d.markNotPickedUp(contract)).toBe(false);
    // Desafio não é falha: nenhum toast de erro, e o diálogo do PIN sabe o ato.
    expect(env.sonner.error).not.toHaveBeenCalled();
    expect(d.managerChallenge.value).toMatchObject({ code: "manager_approval_required", action: "no-show" });
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/WEB-NR/no-show/");
    const first = env.fetchMock.mock.calls[0]![1];
    expect(first.method).toBe("POST");
    expect(first.body).toEqual({ base_revision: "no-show-base", expected_actor_id: 1 });

    expect(await d.authorize({ username: "joyce", pin: "1234" })).toBe(true);
    const second = env.fetchMock.mock.calls[1]![1];
    expect(String(env.fetchMock.mock.calls[1]![0])).toBe("/api/v1/backstage/orders/WEB-NR/no-show/");
    expect(second.body).toEqual({ base_revision: "no-show-base", expected_actor_id: 1, manager_approval: { username: "joyce", pin: "1234" } });
    // A mesma intenção: a assinatura não cria um segundo encerramento.
    expect(second.headers["Idempotency-Key"]).toBe(first.headers["Idempotency-Key"]);
    expect(d.managerChallenge.value).toBeNull();
    // O pedido é relido: a tela mostra o cancelado que o servidor gravou.
    expect(env.refresh).toHaveBeenCalledTimes(1);
  });

  it("tentar o estorno de novo usa a ação do detalhe, pede o gerente e reenvia a MESMA tentativa", async () => {
    // WP-G13: não há prévia nem escolha. A ação `refund-retry` do detalhe traz a base
    // que o comando confere, e a chave da intenção é a chave da tentativa.
    const base = fixtureActions({ can_confirm: true })[0]!;
    env.fetchData.value = { order: { ref: "WEB-ER", actions: [{ ...base, ref: "refund-retry", label: "Tentar o estorno de novo", enabled: true, payload_schema: { base_revision: "refund-base", expected_actor_id: 1 } }] } };
    env.fetchMock.mockRejectedValueOnce({
      status: 422,
      data: { detail: "Tentar o estorno de novo pede a autorização de um gerente.", error: { code: "manager_approval_required" } },
    });
    const d = useOrderDetail("WEB-ER");

    expect(await d.retryRefund()).toBe(false);
    expect(env.sonner.error).not.toHaveBeenCalled();
    expect(d.managerChallenge.value).toMatchObject({ code: "manager_approval_required", action: "refund-retry" });
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/WEB-ER/refund-retry/");
    const first = env.fetchMock.mock.calls[0]![1];
    expect(first.method).toBe("POST");
    expect(first.body).toEqual({ base_revision: "refund-base", expected_actor_id: 1 });

    // O servidor grava a tentativa mesmo quando o gateway recusa: `applied` com o
    // resultado em `refund`. O composable só diz que a tentativa foi gravada.
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied", refund: { outcome: "refused", message: "O Pix não aceitou o estorno. Nada foi devolvido ao cliente. Chame o suporte." } });
    expect(await d.authorize({ username: "joyce", pin: "1234" })).toBe(true);
    const second = env.fetchMock.mock.calls[1]![1];
    expect(second.body).toEqual({ base_revision: "refund-base", expected_actor_id: 1, manager_approval: { username: "joyce", pin: "1234" } });
    // A assinatura não cria uma segunda tentativa: é a mesma chave.
    expect(second.headers["Idempotency-Key"]).toBe(first.headers["Idempotency-Key"]);
    expect(d.managerChallenge.value).toBeNull();
    // O pedido é relido: a linha diz se o dinheiro voltou ou o que o gateway respondeu.
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(env.sonner.success).not.toHaveBeenCalled();

    // Tentativa nova, depois da recusa: outra chave.
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied", refund: { outcome: "refunded" } });
    expect(await d.retryRefund()).toBe(true);
    expect(env.fetchMock.mock.calls[2]![1].headers["Idempotency-Key"]).not.toBe(first.headers["Idempotency-Key"]);
  });

  it("fora do estorno que não saiu, a recusa do servidor vira a frase dele", async () => {
    const base = fixtureActions({ can_confirm: true })[0]!;
    env.fetchData.value = { order: { ref: "WEB-EJ", actions: [{ ...base, ref: "refund-retry", enabled: true, payload_schema: { base_revision: "refund-base", expected_actor_id: 1 } }] } };
    env.fetchMock.mockRejectedValueOnce({
      status: 409,
      data: { detail: "O estorno deste pedido já saiu.", error: { code: "refund_retry_not_allowed" }, outcome: "not_applied" },
    });
    const d = useOrderDetail("WEB-EJ");

    expect(await d.retryRefund()).toBe(false);
    expect(d.managerChallenge.value).toBeNull();
    expect(env.sonner.error).toHaveBeenCalledWith("O estorno deste pedido já saiu.");
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

it("mantém a leitura após 503 e impede nova escrita até atualizar", async () => {
  const data = ref<any>({ order: { ref: "READ-1", actions: fixtureActions({ can_confirm: true }) } });
  const error = ref<any>(null);
  const prior = globalThis.useFetch;
  vi.stubGlobal("useFetch", () => ({ data, error, pending: ref(false), refresh: env.refresh }));
  try {
    env.fetchMock.mockClear();
    const detail = useOrderDetail("READ-1");
    error.value = { statusCode: 503 };
    data.value = null;
    expect(detail.order.value?.ref).toBe("READ-1");
    expect(await detail.confirm()).toBe(false);
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(detail.mutationError.value).toContain("rascunho foi mantido");
  } finally { vi.stubGlobal("useFetch", prior); }
});

it("coalesce dez atualizações do detalhe em uma ativa e uma posterior", async () => {
  env.reset();
  let release!: () => void;
  env.refresh.mockReturnValueOnce(new Promise<void>((resolve) => { release = resolve; })).mockResolvedValue(undefined);
  const detail = useOrderDetail("BURST-DETAIL");
  const reads = Array.from({ length: 10 }, () => detail.refresh());
  expect(env.refresh).toHaveBeenCalledTimes(1);
  release();
  await Promise.all(reads);
  expect(env.refresh).toHaveBeenCalledTimes(2);
});

it("um recibo aplicado continua sucesso quando só a releitura falha", async () => {
  env.reset();
  env.fetchData.value = { order: { actions: fixtureActions({ can_confirm: true }) } };
  env.fetchMock.mockResolvedValue({ outcome: "applied" });
  env.refresh.mockRejectedValue(new Error("synthetic GET failure"));
  const detail = useOrderDetail("APPLIED-READ-FAIL");
  expect(await detail.confirm()).toBe(true);
  expect(detail.mutationError.value).toContain("Ação confirmada");
  expect(env.fetchMock).toHaveBeenCalledTimes(1);
});

// A8-1: a leitura do detalhe não pergunta ao gateway; a tela pede o comando.
describe("useOrderDetail: conferência do cartão", () => {
  beforeEach(() => env.reset());

  it("o pedido que deve cartão pede payment/check/ por POST ao abrir e relê se pagou", async () => {
    env.fetchData.value = { order: { ref: "CARD-1", actions: [] }, payment_check_due: true };
    env.fetchMock.mockResolvedValueOnce({ ok: true, changed: true, payment_check_due: true });
    useOrderDetail("CARD-1");
    await vi.waitFor(() => expect(env.refresh).toHaveBeenCalledTimes(1));
    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/orders/CARD-1/payment/check/", { method: "POST" });
  });

  it("sem mudança no gateway, não relê", async () => {
    env.fetchData.value = { order: { ref: "CARD-2", actions: [] }, payment_check_due: true };
    env.fetchMock.mockResolvedValueOnce({ ok: true, changed: false, payment_check_due: true });
    useOrderDetail("CARD-2");
    await vi.waitFor(() => expect(env.fetchMock).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    expect(env.refresh).not.toHaveBeenCalled();
  });

  it("pedido que não deve cartão não pede nada", () => {
    env.fetchData.value = { order: { ref: "CASH-1", actions: [] }, payment_check_due: false };
    useOrderDetail("CASH-1");
    expect(env.fetchMock).not.toHaveBeenCalled();
  });

  it("a conferência que falha não derruba a tela", async () => {
    env.fetchData.value = { order: { ref: "CARD-3", actions: [] }, payment_check_due: true };
    env.fetchMock.mockRejectedValueOnce(new Error("503"));
    const detail = useOrderDetail("CARD-3");
    await vi.waitFor(() => expect(env.fetchMock).toHaveBeenCalledTimes(1));
    expect(detail.order.value?.ref).toBe("CARD-3");
    expect(env.refresh).not.toHaveBeenCalled();
  });
});
