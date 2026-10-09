import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref } from "vue";

import DetailPage from "~/pages/preorders/[ref].vue";
import PreordersPage from "~/pages/preorders/index.vue";
import { TO_RECEIVE_CLASS } from "~/presentation/preorders";
import type { PreorderCard, PreorderDetail, PreorderListResponse, PreorderSearchResponse } from "~/types/preorders";

import { answerConfirm, useConfirmState } from "../../../operator-kit/app/composables/useConfirm";
import { toneBadge } from "../../../operator-kit/app/presentation/orderDetail";

import { makeProjection } from "../composables/_posSaleHarness";

// A tela única das Encomendas (busca no topo, Dia | Semana, filtros, o lote das
// vias que faltam) e o detalhe — que imprime a Via Pedido e oferece cada gesto (entregar,
// editar, reagendar, cancelar) só quando o servidor diz que pode.

const printOne = vi.fn().mockResolvedValue(true);
const printBatch = vi.fn().mockResolvedValue(true);
const call = vi.fn();
const kick = vi.fn().mockResolvedValue(true);

mockNuxtImport("usePosTerminal", () => async () => ({
  pos: computed(() => makeProjection({ has_open_cash_session: true })),
  pending: ref(false),
  refresh: vi.fn().mockResolvedValue(undefined),
}));
mockNuxtImport("useOperatorLock", () => () => ({ operator: ref({ name: "Ana" }), lock: vi.fn() }));
mockNuxtImport("usePosAction", () => () => ({ call }));
mockNuxtImport("useCounterAgent", () => () => ({ kick }));
mockNuxtImport("usePosOrderTickets", () => () => ({
  printOne,
  printBatch,
  printing: ref(false),
  printingRef: ref(""),
  hasPrinter: ref(true),
  printerUnavailableReason: ref(""),
}));
const navigate = vi.fn().mockResolvedValue(undefined);
mockNuxtImport("navigateTo", () => (...args: unknown[]) => navigate(...args));
// A rota é REATIVA: a tela guarda o estado na query, e o `replace` do router é
// o que muda a tela.
const route = reactive({ params: { ref: "NB-7" }, query: {} as Record<string, string>, path: "/preorders" });
const replace = vi.fn((to: { query: Record<string, string> }) => {
  route.query = { ...to.query };
  return Promise.resolve();
});
mockNuxtImport("useRoute", () => () => route);
mockNuxtImport("useRouter", () => () => ({
  replace,
  afterEach: vi.fn(),
  beforeResolve: vi.fn(),
}));

function card(partial: Partial<PreorderCard> = {}): PreorderCard {
  return {
    ref: "NB-7", channel_display_id: "", customer_name: "Ana Souza", channel_ref: "web",
    channel_label: "Loja online", fulfillment_type: "pickup", fulfillment_label: "Retirada",
    commitment_date: "2026-09-26", commitment_date_display: "hoje", window_label: "9h às 10h",
    window_start: "09:00", status: "accepted", situation: "to_pay", situation_label: "A pagar",
    payment_state: "to_receive",
    total_q: 3600, total_display: "R$ 36,00", balance_q: 3600, balance_display: "R$ 36,00",
    items_summary: "2x Pão", items_count: 2, ticket_printed: false, ...partial,
  };
}

let week: PreorderListResponse;
let detail: PreorderDetail;
let found: PreorderSearchResponse;
const searched = vi.fn();
const listed = vi.fn();

registerEndpoint("/api/v1/backstage/pos/preorders/", (event) => {
  listed(event.path);
  return week;
});
registerEndpoint("/api/v1/backstage/pos/preorders/search/", (event) => {
  searched(event.path);
  return found;
});
registerEndpoint("/api/v1/backstage/pos/preorders/NB-7/", () => ({
  order: detail,
  generated_at: "2026-09-26T12:00:00Z",
  contract_version: 1,
}));
registerEndpoint("/api/v1/backstage/pos/schedule/", () => ({
  ok: true, today: "2026-09-26", date: "2026-09-26", max_preorder_days: 30,
  available_dates: ["2026-09-26", "2026-09-27", "2026-09-28"],
  windows: [{ ref: "slot-09", label: "A partir das 9h" }], earliest_window_ref: "slot-09",
  ready_at: "", bottleneck_name: "", grid: "canonical", is_today: true, readiness_unavailable: false,
}));

const mounted: VueWrapper[] = [];
async function mount(page: unknown) {
  clearNuxtData();
  const wrapper = await mountSuspended(page as never, {
    global: { stubs: { PosFunctionRail: true, RailToggle: true, MoreBelow: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  await flushPromises();
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  week = {
    ok: true, date_from: "2026-09-26", date_to: "2026-10-02", today: "2026-09-26", max_batch: 200,
    count: 2, total_q: 6000, total_display: "R$ 60,00", to_receive_q: 3600, to_receive_display: "R$ 36,00",
    days: Array.from({ length: 7 }, (_, i) => ({
      date: `2026-09-${26 + i}`,
      date_display: "", weekday_display: ["sáb", "dom", "seg", "ter", "qua", "qui", "sex"][i]!,
      day_display: `${26 + i}/09`, is_today: i === 0,
      orders_count: i === 0 ? 2 : 0, total_q: i === 0 ? 6000 : 0,
      total_display: i === 0 ? "R$ 60,00" : "R$ 0,00",
      to_receive_q: i === 0 ? 3600 : 0, to_receive_display: i === 0 ? "R$ 36,00" : "R$ 0,00",
      orders: i === 0 ? [card(), card({ ref: "NB-8", customer_name: "Bia", fulfillment_type: "delivery", fulfillment_label: "Entrega", window_label: "14h às 15h", window_start: "14:00", total_q: 2400, total_display: "R$ 24,00", situation: "paid", situation_label: "Pago", payment_state: "paid", balance_q: 0, balance_display: "R$ 0,00", ticket_printed: true })] : [],
    })),
  };
  detail = {
    ref: "NB-7", status: "accepted", status_label: "Aceito", context: "pos",
    actions: [{ ref: "comment", label: "Comentar", enabled: true, reason: "", payload_schema: { base_revision: "rev-comment" } }],
    channel_ref: "web", channel_icon: "language", total_display: "R$ 36,00",
    customer_name: "Ana Souza", customer_ref: "C-1", customer_phone: "(43) 99988-7766",
    customer_phone_uri: "tel:+5543999887766", customer_whatsapp_url: "https://wa.me/5543999887766",
    customer_email: "", customer_relay_phone: "", customer_relay_code: "", customer_relay_expires_at: "",
    fulfillment_type: "pickup", fulfillment_label: "Retirada", schedule_label: "Hoje · 9h às 10h",
    delivery_address: "", delivery_instructions: "", payment_method_label: "Dinheiro na retirada",
    payment_status_label: "Pendente", payment_link_notice: "", test_order_notice: "",
    is_gift: false, gift_recipient_name: "", gift_recipient_phone: "", gift_message: "", gift_hide_values: false,
    customer_profile: null, fiscal_status_label: "", fiscal_links: [],
    items: [{ sku: "PAO", name: "Pão", qty: "2", unit_price_display: "R$ 18,00", total_display: "R$ 36,00" }],
    customer_note: "Sem açúcar", kitchen_note: "Separar antes das 9h", timeline: [],
    counter: {
      card: card(), ticket_printed: false, revision: "rev-1", actor_id: 7,
      hand_over: {
        allowed: true, needs_payment: true, amount_q: 3600, amount_display: "R$ 36,00",
        suggested_method: "cash", block_reason: "", digital_charge_notice: "",
      },
      cancel: { allowed: true, requires_approval: false, block_reason: "" },
      reschedule: {
        allowed: true, block_reason: "", date: "2026-09-26", slot: "slot-09",
        skus: ["PAO"], revision: "rev-schedule",
      },
      edit: { allowed: true, block_reason: "", cancel_and_redo: false, revision: "rev-edit" },
    },
    managers: [{ username: "gerente", name: "Gerente" }],
    cancellation_presets: [],
  };
  found = {
    ok: true, query: "ana", today: "2026-09-26", include_completed: false, completed_days: 30,
    open_count: 1, open: [card()], completed_count: 0, completed: [],
  };
  printOne.mockClear();
  printBatch.mockClear();
  replace.mockClear();
  searched.mockClear();
  listed.mockClear();
  call.mockReset();
  call.mockResolvedValue({ ok: true, received_q: 3600, status: "completed" });
  kick.mockClear();
  navigate.mockClear();
  route.query = {};
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
});

describe("Detalhe — só lê e imprime a Via Pedido", () => {
  it("mostra quem, quanto falta, os itens e a observação do cliente", async () => {
    const wrapper = await mount(DetailPage);
    const text = wrapper.text();
    expect(text).toContain("Ana Souza");
    expect(wrapper.find("[data-order-detail]").attributes("data-order-context")).toBe("pos");
    expect(wrapper.find("[data-preorder-money]").text()).toBe("A receber R$ 36,00");
    expect(wrapper.find("[data-order-items]").text()).toContain("Pão");
    expect(text).toContain("Sem açúcar");
    expect(wrapper.find("[data-kitchen-note]").text()).toContain("Separar antes das 9h");
  });

  it("imprime a Via Pedido pela impressão individual que já existe", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-print]").trigger("click");
    await flushPromises();
    expect(printOne).toHaveBeenCalledWith("NB-7");
  });

  it("P2: a via que já saiu se reimprime aqui, uma por vez (o lote da seção só leva o que falta)", async () => {
    detail.counter.ticket_printed = true;
    const wrapper = await mount(DetailPage);
    const button = wrapper.find("[data-preorder-print]");
    expect(button.text()).toBe("Imprimir 2ª via");
    await button.trigger("click");
    await flushPromises();
    expect(printOne).toHaveBeenCalledWith("NB-7");
  });

  it("⚠️ nenhum botão morto: Editar só existe quando o servidor diz que pode", async () => {
    detail.counter.edit = {
      ...detail.counter.edit,
      allowed: false,
      block_reason: "Esta encomenda já está pronta: não dá mais para editar.",
    };
    const wrapper = await mount(DetailPage);
    const buttons = wrapper.findAll("button").map((b) => b.text());
    expect(buttons.some((label) => label.includes("Editar"))).toBe(false);
  });
});

const body = () => document.body;
async function settle() {
  await flushPromises();
  await flushPromises();
}

describe("Detalhe — receber e entregar", () => {
  it("com saldo, o botão diz o gesto inteiro com o valor", async () => {
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Receber R$ 36,00 e entregar");
  });

  it("dinheiro com troco: o diálogo mostra o troco e manda a nota e a forma", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    const received = body().querySelector<HTMLInputElement>("[data-preorder-received]")!;
    received.value = "50";
    received.dispatchEvent(new Event("input"));
    await settle();
    expect(body().querySelector("[data-preorder-change]")!.textContent!.replace(/\s/g, " ")).toContain("Troco: R$ 14,00");

    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();

    expect(call).toHaveBeenCalledTimes(1);
    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/pos/preorders/NB-7/hand-over/");
    expect(options.body).toMatchObject({
      base_revision: "rev-1",
      tenders: [{ method: "cash", amount_q: 3600 }],
      cash_tendered_q: 5000,
    });
    expect(options.body.client_request_id).toBeTruthy();
    expect(kick).toHaveBeenCalledWith("preorder_cash");
  });

  it("dinheiro que não cobre o valor não deixa confirmar", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    const received = body().querySelector<HTMLInputElement>("[data-preorder-received]")!;
    received.value = "20";
    received.dispatchEvent(new Event("input"));
    await settle();
    expect(body().querySelector("[data-preorder-change]")!.textContent!.replace(/\s/g, " ")).toContain("não cobre R$ 36,00");
    expect(body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.disabled).toBe(true);
  });

  it("já paga: o gesto é só Entregar, e não manda forma nenhuma", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      needs_payment: false,
      amount_q: 0,
      amount_display: "R$ 0,00",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Entregar");
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();
    expect(call.mock.calls[0]![1].body.tenders).toBeUndefined();
    expect(kick).not.toHaveBeenCalled();
  });

  it("Pix pendente: o diálogo diz que a cobrança do cliente será cancelada antes de receber", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      suggested_method: "",
      digital_charge_notice: "O Pix enviado ao cliente será cancelado.",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Receber R$ 36,00 e entregar");
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    expect(body().querySelector("[data-preorder-digital-charge-notice]")!.textContent).toContain(
      "O Pix enviado ao cliente será cancelado.",
    );
    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();
    expect(call.mock.calls[0]![1].body.tenders).toEqual([{ method: "cash", amount_q: 3600 }]);
  });

  it("o cliente acabou de pagar online: aviso na página e só Entregar", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      digital_charge_notice: "O link de pagamento enviado ao cliente será cancelado.",
    };
    call.mockRejectedValueOnce({
      status: 409,
      data: {
        detail: "O cliente acabou de pagar online. Não receba no balcão: só entregue a encomenda.",
        error: { code: "preorder_paid_online" },
      },
    });
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    // O servidor registrou o pagamento: a leitura seguinte diz que não há saldo.
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      needs_payment: false,
      amount_q: 0,
      amount_display: "R$ 0,00",
      digital_charge_notice: "",
    };
    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();

    expect(body().querySelector("[data-preorder-hand-over-dialog]")).toBeNull();
    expect(wrapper.find("[data-preorder-paid-online]").text()).toContain("acabou de pagar online");
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Entregar");
    expect(kick).not.toHaveBeenCalled();
  });

  it("quando não pode entregar, diz por quê em vez de mostrar botão apagado", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      allowed: false,
      block_reason: "Esta encomenda ainda não está pronta (Em preparo).",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").exists()).toBe(false);
    expect(wrapper.find("[data-preorder-hand-over-blocked]").text()).toContain("ainda não está pronta");
  });
});

describe("Detalhe — as seções do Gestor, no balcão", () => {
  it("cliente e nota fiscal aparecem como no Gestor, quando o servidor manda", async () => {
    detail.customer_profile = {
      orders_label: "12 pedidos", last_order_display: "há 3 dias", average_ticket_display: "",
      favorite_product: "", segment_label: "", segment_tone: "", notes: "",
      dietary_restrictions: "Sem lactose", birthday_display: "", is_birthday_today: false,
    };
    detail.fiscal_status_label = "NFC-e autorizada";
    detail.fiscal_links = [{ label: "DANFE", href: "/danfe/NB-7" }];
    const wrapper = await mount(DetailPage);

    expect(wrapper.find("[data-customer-history]").text()).toBe("12 pedidos · última compra há 3 dias");
    expect(wrapper.find("[data-customer-restrictions]").text()).toBe("Sem lactose");
    expect(wrapper.find("[data-order-fiscal]").text()).toContain("NFC-e autorizada");
  });

  it("comenta no histórico pela rota do Gestor, com a base que o servidor mandou", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-order-comment] textarea").setValue("Cliente vem às 9h30");
    await wrapper.find("[data-order-comment-submit]").trigger("click");
    await flushPromises();

    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/orders/NB-7/comment/");
    expect(options.body).toMatchObject({ note: "Cliente vem às 9h30", base_revision: "rev-comment" });
    expect(options.body.idempotency_key).toBeTruthy();
  });

  it("sem a ação de comentar, o balcão não ganha o campo", async () => {
    detail.actions = [];
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-order-comment]").exists()).toBe(false);
  });

  it("a volta leva ao recorte da lista de onde o operador veio", async () => {
    const wrapper = await mount(DetailPage);
    // Depois de montar: o `mountSuspended` passa pelo `router.replace` (o mock),
    // que zera a query antes de a página existir.
    route.query = { back: "/preorders?mode=week&date=2026-09-26&payment=to_receive" };
    await wrapper.find("[data-preorder-back]").trigger("click");
    expect(navigate).toHaveBeenCalledWith("/preorders?mode=week&date=2026-09-26&payment=to_receive");
  });

  it("uma volta para fora da seção é ignorada (não vira redirecionamento aberto)", async () => {
    const wrapper = await mount(DetailPage);
    route.query = { back: "https://exemplo.com/preorders" };
    await wrapper.find("[data-preorder-back]").trigger("click");
    expect(navigate).not.toHaveBeenCalledWith("https://exemplo.com/preorders");
  });
});

describe("Detalhe — cancelar", () => {
  it("cancela pela rota do Gestor, com a revisão e quem está identificado", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-cancel]").trigger("click");
    await settle();
    const reason = body().querySelector<HTMLTextAreaElement>("[data-reason-input]")!;
    reason.value = "Cliente desistiu";
    reason.dispatchEvent(new Event("input"));
    await settle();
    body().querySelector<HTMLButtonElement>("[data-reason-confirm]")!.click();
    await settle();

    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/orders/NB-7/cancel/");
    expect(options.body).toMatchObject({ reason: "Cliente desistiu", base_revision: "rev-1", expected_actor_id: 7 });
    expect(options.body.idempotency_key).toBeTruthy();
  });

  it("encomenda paga: o servidor pede gerente e o PIN sobe; assinado, o gesto se repete com a assinatura", async () => {
    call.mockRejectedValueOnce({ status: 403, data: { detail: "Precisa de gerente.", error: { code: "manager_approval_required" } } });
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-cancel]").trigger("click");
    await settle();
    body().querySelector<HTMLButtonElement>("[data-reason-confirm]")!.click();
    await settle();

    const auth = wrapper.findComponent({ name: "OperatorManagerAuth" });
    expect(auth.props("open")).toBe(true);
    auth.vm.$emit("authorize", "gerente", "1234");
    await settle();

    expect(call).toHaveBeenCalledTimes(2);
    expect(call.mock.calls[1]![1].body.manager_approval).toEqual({ username: "gerente", pin: "1234" });
    // Mesma tentativa, mesma chave: a primeira foi recusada antes de gravar.
    expect(call.mock.calls[1]![1].body.idempotency_key).toBe(call.mock.calls[0]![1].body.idempotency_key);
  });

  it("o diálogo é o do kit, o mesmo do Gestor: fechar com motivo digitado pergunta na própria tela", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-cancel]").trigger("click");
    await settle();
    expect(wrapper.findComponent({ name: "OperatorReasonDialog" }).exists()).toBe(true);
    const reason = body().querySelector<HTMLTextAreaElement>("[data-reason-input]")!;
    reason.value = "Cliente desistiu";
    reason.dispatchEvent(new Event("input"));
    await settle();
    body().querySelector<HTMLButtonElement>("[data-reason-back]")!.click();
    await settle();
    expect(body().querySelector("[data-reason-discard]")).not.toBeNull();
    body().querySelector<HTMLButtonElement>("[data-reason-keep]")!.click();
    await settle();
    expect(body().querySelector<HTMLTextAreaElement>("[data-reason-input]")!.value).toBe("Cliente desistiu");
    expect(call).not.toHaveBeenCalled();
  });

  it("os motivos prontos do Gestor chegam ao balcão: um toque escolhe o motivo enviado", async () => {
    detail.cancellation_presets = [
      { label: "Cliente", presets: ["Cliente desistiu"] },
      { label: "", presets: ["Pedido em duplicidade"] },
    ];
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-cancel]").trigger("click");
    await settle();
    const chips = [...body().querySelectorAll<HTMLButtonElement>("[data-reason-preset]")];
    expect(chips.map((chip) => chip.textContent?.trim())).toEqual(["Cliente desistiu", "Pedido em duplicidade"]);
    expect(body().querySelector("[data-testid='reason-other']")).not.toBeNull();
    chips[0]!.click();
    await settle();
    body().querySelector<HTMLButtonElement>("[data-reason-confirm]")!.click();
    await settle();

    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/orders/NB-7/cancel/");
    expect(options.body).toMatchObject({ reason: "Cliente desistiu" });
  });

  it("sem permissão para cancelar, não há botão", async () => {
    detail.counter.cancel = {
      allowed: false,
      requires_approval: false,
      block_reason: "Pedido do iFood: cancele pelo Gestor de pedidos.",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-cancel]").exists()).toBe(false);
  });
});

describe("Detalhe — o painel do Balcão (S5 do redesenho)", () => {
  it("P3: o saldo e os gestos moram num painel à parte do detalhe do kit, fixo à direita em tela larga", async () => {
    const wrapper = await mount(DetailPage);
    const layout = wrapper.find("[data-preorder-layout]");
    expect(layout.classes()).toEqual(expect.arrayContaining(["grid", "lg:grid-cols-[minmax(0,1fr)_23rem]"]));
    const panel = layout.find("[data-preorder-counter-panel]");
    expect(panel.attributes("aria-label")).toBe("Balcão");
    expect(panel.classes()).toEqual(expect.arrayContaining(["lg:sticky", "lg:col-start-2", "lg:row-start-1"]));
    expect(panel.find("h1").text()).toBe("Ana Souza");
    expect(panel.find("[data-preorder-money]").text()).toBe("A receber R$ 36,00");
    expect(panel.find("[data-preorder-hand-over]").exists()).toBe(true);
    // O detalhe do kit fica sem o que é do balcão (o PDV não usa #summary nem #actions).
    const kit = layout.find("[data-order-detail]");
    expect(kit.classes()).toContain("lg:col-start-1");
    expect(kit.find("[data-preorder-money]").exists()).toBe(false);
    expect(kit.find("[data-preorder-hand-over]").exists()).toBe(false);
    // Tela estreita: uma árvore só, e o painel vem ANTES do detalhe.
    const children = [...layout.element.children];
    expect(children.indexOf(panel.element)).toBeLessThan(children.indexOf(kit.element));
  });

  it("o nome no topo do painel não repete o número e o canal, que o resumo do kit já diz", async () => {
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-counter-panel]").text()).not.toContain("Loja online");
    expect(wrapper.find("[data-order-summary]").text()).toContain("web");
  });

  it("hierarquia dos gestos: o principal na largura, os médios lado a lado, Cancelar separado no pé", async () => {
    const wrapper = await mount(DetailPage);
    const panel = wrapper.find("[data-preorder-counter-panel]");
    expect(panel.find("[data-preorder-hand-over]").classes()).toContain("w-full");
    const middle = panel.find("[data-preorder-actions]");
    expect(middle.classes()).toEqual(expect.arrayContaining(["flex", "flex-wrap"]));
    for (const gesture of ["reschedule", "print", "edit"]) {
      const button = middle.find(`[data-preorder-${gesture}]`);
      expect(button.classes()).toContain("flex-auto");
      expect(button.classes()).not.toContain("w-full");
    }
    // Cancelar não está entre os gestos do dia a dia: fica no pé, separado por um
    // traço, e sem borda nem fundo (ação perigosa não ganha destaque maior).
    expect(middle.find("[data-preorder-cancel]").exists()).toBe(false);
    const zone = panel.find("[data-preorder-cancel-zone]");
    expect(zone.classes()).toContain("border-t");
    expect(panel.element.lastElementChild).toBe(zone.element);
    const cancel = zone.find("[data-preorder-cancel]");
    expect(cancel.classes()).toContain("text-error");
    expect(cancel.classes()).not.toContain("ring");
  });

  it("Comentar no painel leva ao campo do histórico, que continua do kit", async () => {
    const wrapper = await mount(DetailPage);
    const shortcut = wrapper.find("[data-preorder-counter-panel] [data-preorder-comment-shortcut]");
    expect(shortcut.text()).toBe("Comentar no histórico");
    const field = wrapper.find("[data-order-comment] textarea").element as HTMLTextAreaElement;
    const focus = vi.spyOn(field, "focus");
    await shortcut.trigger("click");
    await settle();
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    expect(focus).toHaveBeenCalled();
  });

  it("sem a ação de comentar, o painel não oferece o atalho", async () => {
    detail.actions = [];
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-comment-shortcut]").exists()).toBe(false);
  });

  it("P5: uma etiqueta de estado só, a do balcão; a do pedido (a do Gestor) não aparece no PDV", async () => {
    detail.counter.card = card({ status: "ready", situation: "ready", situation_label: "Pronto" });
    const wrapper = await mount(DetailPage);
    expect(wrapper.findAll("[data-preorder-situation]")).toHaveLength(1);
    expect(wrapper.find("[data-order-status]").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Aceito");
  });

  it("sem permissão para cancelar, o pé do painel some junto com o botão", async () => {
    detail.counter.cancel = { allowed: false, requires_approval: false, block_reason: "" };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-cancel-zone]").exists()).toBe(false);
  });
});

const refsIn = (wrapper: { findAll: (s: string) => { attributes: (n: string) => string | undefined }[] }) =>
  wrapper.findAll("[data-preorder]").map((c) => c.attributes("data-preorder"));

type Mounted = Awaited<ReturnType<typeof mount>>;
type HeaderAction = { label: string; disabled?: boolean; reason?: string; onSelect?: () => void };

/** O cabeçalho do kit, com as ações declaradas como dados (o ⋯ "Mais ações"). */
function header(wrapper: Mounted) {
  return wrapper.findComponent({ name: "OperatorPageHeader" });
}

/** A ação do ⋯ que começa com o rótulo (o lote das Vias Pedido, Atualizar). */
function headerAction(wrapper: Mounted, label: string | RegExp): HeaderAction | undefined {
  const actions = (header(wrapper).props("actions") ?? []) as HeaderAction[];
  return actions.find((action) => (typeof label === "string" ? action.label === label : label.test(action.label)));
}

/** O lote das Vias Pedido no ⋯ (o rótulo diz quantas). */
function printAction(wrapper: Mounted): HeaderAction | undefined {
  return headerAction(wrapper, /Via Pedido|vias impressas|via para imprimir/);
}

/** O painel de filtros único da suíte. */
function panel(wrapper: Mounted) {
  return wrapper.findComponent({ name: "OperatorFilterPanel" });
}

/** O painel devolve o recorte (o que um toque num filtro rápido ou completo faz). */
async function setPanel(wrapper: Mounted, filters: Record<string, string[]>) {
  panel(wrapper).vm.$emit("update:modelValue", filters);
  await flushPromises();
}

/** Os recortes ativos que o cabeçalho mostra como chips (no celular) e o painel (na mesa). */
function activeLabels(wrapper: Mounted): string[] {
  return ((header(wrapper).props("activeFilters") ?? []) as { label: string }[]).map((filter) => filter.label);
}

/** "Cliente veio buscar": o que se digita na busca da tela. */
async function typeSearch(wrapper: Mounted, value: string) {
  wrapper.findComponent({ name: "OperatorSuiteSearch" }).vm.$emit("update:modelValue", value);
  await new Promise((resolve) => setTimeout(resolve, 300));
  await flushPromises();
  await flushPromises();
}

describe("Encomendas — a semana no centro", () => {
  it("abre na semana: sete dias numa única árvore responsiva, com conta e vazio por extenso", async () => {
    const wrapper = await mount(PreordersPage);
    const columns = wrapper.find("[data-week-grid]").findAll("[data-week-day]");
    expect(columns).toHaveLength(7);
    expect(columns[0]!.find("[data-week-day-total]").text()).toBe("2 encomendas · R$ 60,00");
    expect(columns[0]!.find("[data-week-day-to-receive]").text()).toBe("A receber R$ 36,00");
    expect(columns[1]!.find("[data-week-day-total]").text()).toBe("Nenhuma encomenda");
    expect(columns[1]!.find("[data-week-day-to-receive]").exists()).toBe(false);
    // A mesma árvore responde a qualquer largura: não duplica cards escondidos.
    expect(wrapper.findAll("[data-week-board]")).toHaveLength(1);
    expect(wrapper.find("[data-week-grid]").findAll("[data-preorder]")).toHaveLength(2);
    expect(wrapper.find("[data-preorders-total]").text()).toBe("2 encomendas · R$ 60,00");
    expect(wrapper.find("[data-preorders-to-receive]").text()).toBe("A receber R$ 36,00");
  });

  it("o card da grade: saldo em destaque ou 'pago', e o sinal da Via Pedido impressa", async () => {
    const wrapper = await mount(PreordersPage);
    const grid = wrapper.find("[data-week-grid]");
    expect(grid.find('[data-preorder="NB-7"] [data-preorder-money]').text()).toBe("A receber R$ 36,00");
    expect(grid.find('[data-preorder="NB-8"] [data-preorder-money]').text()).toBe("R$ 24,00 pago");
    expect(grid.find('[data-preorder="NB-8"] [data-preorder-printed]').exists()).toBe(true);
    expect(grid.find('[data-preorder="NB-7"] [data-preorder-printed]').exists()).toBe(false);
    expect(grid.find('[data-preorder="NB-7"]').attributes("href")).toBe("/preorders/NB-7");
  });

  it("hoje tem destaque e diz o dia da semana, com 'Hoje' uma vez só", async () => {
    const wrapper = await mount(PreordersPage);
    const opens = wrapper.find("[data-week-grid]").findAll("[data-week-day-open]");
    const today = opens[0]!;
    expect(today.attributes("aria-current")).toBe("date");
    expect(today.find("[data-week-day-title]").text()).toMatch(/^Hoje, \S+ 26\/09$/);
    expect(today.text().match(/Hoje/g)).toHaveLength(1);
    expect(opens[1]!.attributes("aria-current")).toBeUndefined();
    expect(opens[1]!.find("[data-week-day-title]").text()).not.toContain("Hoje");
  });

  it("tocar no dia da grade abre o modo Dia naquela data", async () => {
    const wrapper = await mount(PreordersPage);
    await wrapper.find("[data-week-grid]").findAll("[data-week-day-open]")[0]!.trigger("click");
    expect(route.query).toEqual({ mode: "day", date: "2026-09-26" });
  });

  it("‹ › anda de semana em semana, e a volta para hoje aparece fora da semana de hoje", async () => {
    const wrapper = await mount(PreordersPage);
    expect(wrapper.find("[data-period-today]").exists()).toBe(false);
    await wrapper.find("[data-period-next]").trigger("click");
    await flushPromises();
    expect(route.query.date).toBeTruthy();
    expect(wrapper.find("[data-period-today]").exists()).toBe(true);
    expect(wrapper.find("[data-period-next]").attributes("aria-label")).toBe("Próxima semana");
  });

  it("semana sem nada diz por extenso — zero não é código", async () => {
    week = { ...week, count: 0, days: week.days.map((d) => ({ ...d, orders: [], orders_count: 0 })) };
    const wrapper = await mount(PreordersPage);
    expect(wrapper.find("[data-preorders-empty]").text()).toBe("Nenhuma encomenda nesta semana.");
    expect(wrapper.find("[data-preorders-print]").exists()).toBe(false);
  });
});

describe("Encomendas — um controle por estado, uma porta por destino", () => {
  it("R1: Dia | Semana mora só no Período; o cabeçalho do topo não tem abas", async () => {
    const wrapper = await mount(PreordersPage);
    const bar = wrapper.find("[data-operator-page-header]");
    expect(bar.exists()).toBe(true);
    expect(bar.find("nav").exists()).toBe(false);
    expect(bar.findAll("[data-section]")).toHaveLength(0);
    expect(wrapper.find("[data-period-next]").exists()).toBe(true);
  });

  it("R2: o cabeçalho diz 'Encomendas' sem ser segundo link para a seção (a porta é o rail)", async () => {
    const wrapper = await mount(PreordersPage);
    const bar = wrapper.find("[data-operator-page-header]");
    expect(bar.find("h1").text()).toBe("Encomendas");
    // O único link possível ali é o selo do app no celular, que volta à Central.
    expect(bar.findAll("a").filter((a) => a.attributes("data-page-header-app") === undefined)).toHaveLength(0);
    expect(bar.find('a[href="/preorders"]').exists()).toBe(false);
  });

  it("R3: o 'A receber' tem a mesma frase e o mesmo peso no período, no dia e na encomenda", async () => {
    const wrapper = await mount(PreordersPage);
    const period = wrapper.find("[data-preorders-to-receive]");
    const day = wrapper.find("[data-week-day-to-receive]");
    const row = wrapper.find('[data-preorder="NB-7"] [data-preorder-money]');
    for (const node of [period, day, row]) {
      expect(node.text()).toBe("A receber R$ 36,00");
      expect(node.classes().join(" ")).toBe(TO_RECEIVE_CLASS);
    }
  });

  it("R4: o selo de situação é a peça do kit, na linha e no detalhe", async () => {
    // Na linha, o selo só aparece quando diz o que o dinheiro não diz ("Pronto").
    week.days[0]!.orders[0] = card({ situation: "ready", situation_label: "Pronto" });
    const list = await mount(PreordersPage);
    expect(list.find('[data-preorder="NB-7"] [data-preorder-situation]').classes())
      .toEqual(expect.arrayContaining(toneBadge("success").split(" ")));
    detail.counter.card = card({ status: "ready", situation: "ready", situation_label: "Pronto" });
    const page = await mount(DetailPage);
    expect(page.find("[data-preorder-situation]").classes())
      .toEqual(expect.arrayContaining(toneBadge("success").split(" ")));
  });

  it("R5: no detalhe, a etiqueta de dinheiro não repete a linha do saldo (a régua da linha da lista)", async () => {
    const money = [
      card(),
      card({ situation: "paid", situation_label: "Pago", payment_state: "paid", balance_q: 0, balance_display: "R$ 0,00" }),
      card({ situation: "on_account", situation_label: "Na conta da casa", payment_state: "on_account", balance_q: 0, balance_display: "R$ 0,00" }),
      card({ situation: "check_payment", situation_label: "Conferir pagamento", payment_state: "check", balance_q: null, balance_display: "" }),
    ];
    const lines = ["A receber R$ 36,00", "R$ 36,00 pago", "R$ 36,00 na conta da casa", "R$ 36,00 · pagamento a conferir"];
    for (const [i, situation] of money.entries()) {
      detail.counter.card = situation;
      const page = await mount(DetailPage);
      expect(page.find("[data-preorder-situation]").exists()).toBe(false);
      expect(page.find("[data-preorder-money]").text()).toBe(lines[i]);
    }
    for (const [situation, label] of [["ready", "Pronto"], ["out_for_delivery", "Saiu para entrega"], ["delivered", "Entregue"]] as const) {
      detail.counter.card = card({ situation, situation_label: label });
      const page = await mount(DetailPage);
      expect(page.find("[data-preorder-situation]").text()).toBe(label);
    }
    // Sete detalhes montados em sequência: o teto padrão (5 s) é curto com a suíte inteira rodando.
  }, 20_000);
});

describe("Encomendas — o dia", () => {
  it("o modo Dia agrupa pela janela, com a linha inteira", async () => {
    const wrapper = await mount(PreordersPage);
    await wrapper.find("[data-week-grid]").findAll("[data-week-day-open]")[0]!.trigger("click");
    await flushPromises();
    const windows = wrapper.find("[data-preorders-day]").findAll("[data-preorders-window]");
    expect(windows.map((w) => w.find("h3").text())).toEqual(["9h às 10h", "14h às 15h"]);
    expect(wrapper.find("[data-period-next]").attributes("aria-label")).toBe("Próximo dia");
  });
});

describe("Encomendas — filtros e o lote das vias que faltam", () => {
  it("o painel de filtros da suíte: os recortes de todo dia como filtros rápidos, com contagem nos completos; o filtro vai para a URL", async () => {
    const wrapper = await mount(PreordersPage);
    expect(panel(wrapper).exists()).toBe(true);
    expect((panel(wrapper).props("quick") as { label: string }[]).map((quick) => quick.label))
      .toEqual(["A receber", "Sem Via Pedido", "Retiradas", "Entregas"]);
    const dimensions = panel(wrapper).props("dimensions") as { id: string; options: { label: string; count: number }[] }[];
    expect(dimensions.map((dimension) => dimension.id)).toEqual(["fulfillment", "pay", "print"]);
    expect(dimensions.find((dimension) => dimension.id === "pay")!.options.map((option) => [option.label, option.count]))
      .toEqual([["A receber", 1], ["Pagas", 1]]);
    await setPanel(wrapper, { fulfillment: ["delivery"] });
    expect(route.query).toEqual({ fulfillment: "delivery" });
    expect(refsIn(wrapper.find("[data-week-grid]"))).toEqual(["NB-8"]);
    expect(activeLabels(wrapper)).toEqual(["Recebimento: Entregas"]);
    // O card leva o recorte ao detalhe: a volta cai na semana filtrada, não na casa.
    expect(wrapper.find('[data-week-grid] [data-preorder="NB-8"]').attributes("href"))
      .toBe("/preorders/NB-8?back=%2Fpreorders%3Ffulfillment%3Ddelivery");
  });

  it("Retiradas e Entregas se excluem: o filtro rápido novo vence o que já estava", async () => {
    route.query = { fulfillment: "pickup" };
    const wrapper = await mount(PreordersPage);
    // O painel SOMA o filtro rápido na dimensão; a tela fica com o último tocado.
    await setPanel(wrapper, { fulfillment: ["pickup", "delivery"] });
    expect(route.query).toEqual({ fulfillment: "delivery" });
    // Tocar de novo desliga: a dimensão volta a "Todas".
    await setPanel(wrapper, {});
    expect(route.query).toEqual({});
  });

  it("P2: o lote imprime só a via que ainda não saiu, mesmo com a impressa na tela", async () => {
    const wrapper = await mount(PreordersPage);
    // Sem recorte, as duas estão na grade: NB-8 já tem a Via Pedido, NB-7 não.
    expect(refsIn(wrapper.find("[data-week-grid]"))).toEqual(["NB-7", "NB-8"]);
    const print = printAction(wrapper)!;
    expect(print.label).toBe("Imprimir a Via Pedido de 1 encomenda");
    expect(print.disabled).toBe(false);
    print.onSelect!();
    await flushPromises();
    expect(printBatch).toHaveBeenCalledWith({ date_from: "2026-09-26", date_to: "2026-10-02", refs: ["NB-7"] });
  });

  it("'Sem Via Pedido' mostra só o que não saiu, e o lote leva as mesmas", async () => {
    const wrapper = await mount(PreordersPage);
    await setPanel(wrapper, { print: ["pending"] });
    expect(route.query).toEqual({ print: "pending" });
    expect(refsIn(wrapper.find("[data-week-grid]"))).toEqual(["NB-7"]);
    const print = printAction(wrapper)!;
    expect(print.label).toBe("Imprimir a Via Pedido de 1 encomenda");
    print.onSelect!();
    await flushPromises();
    expect(printBatch).toHaveBeenCalledWith({ date_from: "2026-09-26", date_to: "2026-10-02", refs: ["NB-7"] });
  });

  it("P2: com todas as vias impressas o lote não reimprime, e a ação desligada diz o que há", async () => {
    week.days[0]!.orders[0] = card({ ticket_printed: true });
    const wrapper = await mount(PreordersPage);
    const print = printAction(wrapper)!;
    expect(print.label).toBe("Todas as vias impressas");
    expect(print.disabled).toBe(true);
  });

  it("filtro que esvazia a semana diz o que não há; limpar é gesto do painel, e só dele", async () => {
    const wrapper = await mount(PreordersPage);
    route.query.pay = "on_account";
    await flushPromises();
    const empty = wrapper.find("[data-preorders-filter-empty]");
    expect(empty.text()).toContain("Nenhuma encomenda com estes filtros nesta semana.");
    // R5: o vazio não repete o "limpar" do painel (antes: um "Mostrar todas" aqui).
    expect(empty.find("button").exists()).toBe(false);
    expect(activeLabels(wrapper)).toEqual(["Pagamento: Na conta da casa"]);
    expect(printAction(wrapper)!.label).toBe("Nenhuma via para imprimir");
  });

  it("pagamento a conferir ganha aviso da tela, com o gesto de ver só elas", async () => {
    week.days[0]!.orders.push(card({ ref: "NB-9", payment_state: "check", balance_q: null, situation: "check_payment" }));
    const wrapper = await mount(PreordersPage);
    const alerts = header(wrapper).props("alerts") as { title: string; color: string; action?: { label: string } }[];
    expect(alerts).toHaveLength(1);
    expect(alerts[0]!.title).toContain("1 encomenda está com o pagamento a conferir");
    expect(alerts[0]!.color).toBe("warning");
    expect(alerts[0]!.action?.label).toBe("Mostrar só essas");
    expect(wrapper.find("[data-page-header-alert]").text()).toContain("pagamento a conferir");
  });

  it("'Mostrar só essas' liga o recorte, e a volta é o X do chip: o aviso não vira segundo 'limpar'", async () => {
    week.days[0]!.orders.push(card({ ref: "NB-9", payment_state: "check", balance_q: null, situation: "check_payment" }));
    const wrapper = await mount(PreordersPage);
    const [alert] = header(wrapper).props("alerts") as { action: { onSelect: () => void } }[];
    alert!.action.onSelect();
    await flushPromises();
    expect(route.query).toEqual({ pay: "check" });
    expect(header(wrapper).props("alerts")).toEqual([]);
    expect(activeLabels(wrapper)).toEqual(["Pagamento: A conferir"]);
    expect(wrapper.text()).not.toContain("Mostrar todas");
  });
});

describe("Encomendas: a tela da seção (S3 do redesenho)", () => {
  it("o Período mora na toolbar da seção, e sai durante a busca", async () => {
    const wrapper = await mount(PreordersPage);
    expect(wrapper.findAll("[data-period-picker]")).toHaveLength(1);
    expect(wrapper.find("[data-page-header-filters] [data-period-picker]").exists()).toBe(true);
    await typeSearch(wrapper, "Ana");
    expect(wrapper.find("[data-period-picker]").exists()).toBe(false);
    expect(panel(wrapper).exists()).toBe(false);
  });

  it("a linha 'Hoje': para entregar, a receber e as vias que faltam, com o peso do 'A receber'", async () => {
    const wrapper = await mount(PreordersPage);
    const today = wrapper.find("[data-preorders-today]");
    expect(today.findAll("[data-preorders-today-fact]").map((f) => f.text()))
      .toEqual(["2 para entregar", "A receber R$ 36,00", "1 sem Via Pedido"]);
    expect(today.find('[data-preorders-today-fact="to_receive"]').classes().join(" ")).toBe(TO_RECEIVE_CLASS);
  });

  it("'Hoje' é sempre de hoje: fora da semana de hoje, vem da leitura do selo, sem pergunta nova", async () => {
    week = { ...week, days: week.days.map((d) => ({ ...d, is_today: false })) };
    clearNuxtData();
    useNuxtData<PreorderListResponse>("pos-preorders-ahead").data.value = {
      ...week,
      days: [{ ...week.days[0]!, is_today: true, orders: [card({ ref: "HOJE-1", ticket_printed: true })] }],
    };
    const wrapper = await mountSuspended(PreordersPage as never, {
      global: { stubs: { PosFunctionRail: true, RailToggle: true, MoreBelow: true } },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    await flushPromises();
    await flushPromises();
    expect(wrapper.findAll("[data-preorders-today-fact]").map((f) => f.text()))
      .toEqual(["1 para entregar", "A receber R$ 36,00", "Todas as vias impressas"]);
    // Uma leitura só: a do período. A linha "Hoje" não pergunta nada ao servidor.
    expect(listed).toHaveBeenCalledTimes(1);
  });

  it("o resumo do período diz de que período fala, e some quando o período é só hoje", async () => {
    const wrapper = await mount(PreordersPage);
    expect(wrapper.find("[data-preorders-summary]").text()).toContain("Na semana");
    // Um dia que não é hoje (a data do teste é fixa; o relógio, não).
    await wrapper.find("[data-week-grid]").findAll("[data-week-day-open]")[0]!.trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-preorders-summary]").text()).toContain("No dia");
    // O dia de hoje (sem `date` na URL): a linha "Hoje" já diz, o resumo sai.
    route.query = { mode: "day" };
    await flushPromises();
    expect(wrapper.find("[data-preorders-summary]").exists()).toBe(false);
    expect(wrapper.find("[data-preorders-today]").exists()).toBe(true);
  });

  it("a linha da encomenda: a janela primeiro, o número e os itens, e 'Via impressa' escrita", async () => {
    const wrapper = await mount(PreordersPage);
    const ana = wrapper.find('[data-week-grid] [data-preorder="NB-7"]');
    expect(ana.find("[data-preorder-window]").text()).toBe("09:00");
    expect(ana.text()).toContain("NB-7 · Loja online · Retirada · 2 itens");
    // "A pagar" já está no dinheiro: o selo não repete.
    expect(ana.find("[data-preorder-situation]").exists()).toBe(false);
    expect(wrapper.find('[data-week-grid] [data-preorder="NB-8"] [data-preorder-printed]').text()).toBe("Via impressa");
  });

  it("R7: o dia vazio diz uma vez só, no cabeçalho", async () => {
    const wrapper = await mount(PreordersPage);
    const empty = wrapper.find("[data-week-grid]").findAll("[data-week-day]")[1]!;
    expect(empty.text()).toBe(empty.find("[data-week-day-open]").text());
    expect(empty.text().match(/encomenda/gi)).toHaveLength(1);
    expect(wrapper.text()).not.toContain("Dia livre");
  });

  it("a nota de escopo é legenda: vem depois da grade, não na linha do período", async () => {
    const wrapper = await mount(PreordersPage);
    const html = wrapper.html();
    expect(html.indexOf("data-preorders-scope")).toBeGreaterThan(html.indexOf("data-week-board"));
    expect(wrapper.find("[data-preorders-scope]").text()).toBe("Retiradas e entregas de todos os canais, pela data combinada.");
  });
});

describe("Encomendas — Cliente veio buscar", () => {
  it("é a busca da tela no cabeçalho, com a frase que diz o que se pode procurar", async () => {
    const wrapper = await mount(PreordersPage);
    const search = wrapper.findComponent({ name: "OperatorSuiteSearch" });
    // A busca da suíte com o alcance "Esta tela" (`v-model`): uma busca só no cabeçalho.
    expect(wrapper.findAllComponents({ name: "OperatorSuiteSearch" })).toHaveLength(1);
    expect(search.props("modelValue")).toBe("");
    expect(search.props("placeholder")).toBe("Nome, telefone, CPF ou CNPJ, endereço ou número do pedido");
    expect(search.props("ariaLabel")).toBe("Procurar encomenda por nome, telefone, CPF ou CNPJ, endereço ou número do pedido");
    expect(wrapper.find("[data-page-header-search] [data-suite-search]").exists()).toBe(true);
    // "Incluir concluídas" só vale para a busca: sem busca digitada, não aparece.
    expect(wrapper.find("[data-preorders-include-completed]").exists()).toBe(false);
    await typeSearch(wrapper, "Ana");
    expect(wrapper.find("[data-preorders-include-completed]").exists()).toBe(true);
    // O alcance "Esta tela" diz quantas a tela achou.
    expect(wrapper.findComponent({ name: "OperatorSuiteSearch" }).props("screenCount")).toBe(1);
  });

  it("digitar troca o período pelo resultado em aberto, e a busca vai para a URL", async () => {
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    expect(route.query).toEqual({ q: "Ana" });
    expect(wrapper.find("[data-week-grid]").exists()).toBe(false);
    expect(refsIn(wrapper.find('[data-preorders-results="open"]'))).toEqual(["NB-7"]);
    expect(wrapper.find('[data-preorders-results="completed"]').exists()).toBe(false);
  });

  it("nada em aberto: a tela oferece as concluídas, e um toque liga o filtro", async () => {
    found = { ...found, open_count: 0, open: [] };
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    const empty = wrapper.find("[data-preorders-open-empty]");
    expect(empty.text()).toContain("Nenhuma encomenda em aberto para “Ana”.");
    await empty.find("[data-preorders-offer-completed]").trigger("click");
    expect(route.query).toEqual({ q: "Ana", completed: "1" });
  });

  it("com as concluídas, elas vêm numa seção SEPARADA, abaixo das em aberto", async () => {
    found = {
      ...found, include_completed: true, completed_count: 1,
      completed: [card({ ref: "NB-1", situation: "delivered", situation_label: "Entregue" })],
    };
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    const toggle = wrapper.find("[data-preorders-include-completed]");
    await (toggle.element.matches("button") ? toggle : toggle.find("button")).trigger("click");
    await flushPromises();
    expect(route.query).toEqual({ q: "Ana", completed: "1" });
    expect(refsIn(wrapper.find('[data-preorders-results="open"]'))).toEqual(["NB-7"]);
    const completed = wrapper.find('[data-preorders-results="completed"]');
    expect(completed.find("h2").text()).toBe("1 concluída nos últimos 30 dias");
    expect(refsIn(completed)).toEqual(["NB-1"]);
  });

  it("um resultado só: Enter abre o detalhe, e a volta cai de novo na busca", async () => {
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(navigate).toHaveBeenCalledWith("/preorders/NB-7?back=%2Fpreorders%3Fq%3DAna");
  });

  it("leitor de código com o foco fora de campo: a leitura vira a busca da tela", async () => {
    const wrapper = await mount(PreordersPage);
    for (const key of "NB-7") document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 300));
    await flushPromises();
    expect(wrapper.findComponent({ name: "OperatorSuiteSearch" }).props("modelValue")).toBe("NB-7");
    expect(route.query).toEqual({ q: "NB-7" });
  });
});

describe("Encomendas — Nova encomenda (S9, P6 do dono)", () => {
  it("a seção tem a porta: leva à venda já no modo Encomendas", async () => {
    const wrapper = await mount(PreordersPage);
    const button = wrapper.find("[data-preorders-new]");
    expect(button.exists()).toBe(true);
    expect(button.text()).toBe("Nova encomenda");
    await button.trigger("click");
    expect(navigate).toHaveBeenCalledWith({ path: "/", query: { new: "order" } });
  });

  it("a porta é a ação primária do cabeçalho e não sai durante a busca: quem não achou a encomenda anota uma nova", async () => {
    const wrapper = await mount(PreordersPage);
    expect(wrapper.find("[data-page-header-actions] [data-preorders-new]").exists()).toBe(true);
    await typeSearch(wrapper, "Ana");
    expect(wrapper.find("[data-preorders-new]").exists()).toBe(true);
  });
});

describe("Encomendas: a arrumação do balcão (OBS0310-D)", () => {
  afterEach(() => {
    try { localStorage.clear(); } catch { /* sem armazenamento no ambiente */ }
    answerConfirm(false);
  });

  it("de cima para baixo: o cabeçalho (busca, Nova encomenda, ⋯), a toolbar (período, filtros, grade/lista, Hoje) e os cards", async () => {
    const wrapper = await mount(PreordersPage);
    const toolbar = wrapper.find("[data-page-header-filters]");
    expect(toolbar.find("[data-period-picker]").exists()).toBe(true);
    expect(toolbar.find("[data-operator-filter-panel-root]").exists()).toBe(true);
    expect(toolbar.findAll("[data-preorders-layout-option]").map((b) => b.attributes("aria-label"))).toEqual(["Ver em grade", "Ver em lista"]);
    expect(toolbar.find("[data-preorders-today]").exists()).toBe(true);
    // O lote e Atualizar moram no ⋯ (agem sobre a tela inteira).
    expect(printAction(wrapper)).toBeDefined();
    expect(headerAction(wrapper, "Atualizar")).toBeDefined();
    const html = wrapper.html();
    const order = ["data-page-header-search", "data-preorders-new", "data-period-picker", "data-operator-filter-panel-root", "data-preorders-today", "data-week-board"]
      .map((marker) => html.indexOf(marker));
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("no celular, 'Ler código da encomenda' é a ação na base (a peça do kit)", async () => {
    const wrapper = await mount(PreordersPage);
    const bar = wrapper.find("[data-operator-action-bar]");
    expect(bar.exists()).toBe(true);
    expect(bar.text()).toContain("Ler código da encomenda");
    expect(bar.classes()).toContain("lg:hidden");
  });

  it("grade ou lista: a semana vira um dia embaixo do outro, e a escolha fica no dispositivo", async () => {
    const wrapper = await mount(PreordersPage);
    const grid = wrapper.find('[data-preorders-layout-option="grid"]');
    expect(grid.attributes("aria-pressed")).toBe("true");
    expect(wrapper.find("[data-week-grid]").exists()).toBe(true);
    await wrapper.find('[data-preorders-layout-option="list"]').trigger("click");
    expect(wrapper.find('[data-preorders-layout-option="list"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.find("[data-week-grid]").exists()).toBe(false);
    expect(wrapper.find("[data-week-list]").findAll("[data-week-day]")).toHaveLength(7);
    // Arrumação não é recorte: a URL não muda.
    expect(route.query).toEqual({});
    expect(localStorage.getItem("pos.preordersLayout")).toBe("list");
    const again = await mount(PreordersPage);
    expect(again.find("[data-week-list]").exists()).toBe(true);
  });

  it("arrastar o card para outro dia pergunta no diálogo da casa e reagenda pela rota do Reagendar", async () => {
    const wrapper = await mount(PreordersPage);
    const ana = wrapper.find('[data-preorder-card="NB-7"]');
    expect(ana.attributes("draggable")).toBe("true");
    // O link não se arrasta (senão o navegador levaria o endereço, e não o card).
    expect(ana.find('[data-preorder="NB-7"]').attributes("draggable")).toBe("false");
    await ana.trigger("dragstart");
    const monday = wrapper.find('[data-week-day="2026-09-28"]');
    await monday.trigger("dragover");
    expect(monday.attributes("data-drop-target")).toBe("over");
    await monday.trigger("drop");
    await flushPromises();
    const asked = useConfirmState().pending.value;
    expect(asked?.title).toBe("Mudar a encomenda de Ana Souza para seg, 28/09?");
    expect(asked?.description).toBe("O cliente será avisado da nova data. O horário combinado continua: 9h às 10h.");
    expect(asked?.confirmLabel).toBe("Mudar para seg, 28/09");
    // Mudar de dia é ato normal: o botão na cor da casa, não o vermelho de descartar.
    expect(asked?.tone).toBe("primary");
    expect(call).not.toHaveBeenCalled();
    answerConfirm(true);
    await flushPromises();
    expect(call).toHaveBeenCalledWith("/api/v1/backstage/orders/NB-7/reschedule/", {
      body: expect.objectContaining({ date: "2026-09-28", slot: "slot-09", reason: "", base_revision: "rev-schedule", expected_actor_id: 7 }),
    });
  });

  it("desistir na pergunta não muda nada", async () => {
    const wrapper = await mount(PreordersPage);
    await wrapper.find('[data-preorder-card="NB-7"]').trigger("dragstart");
    const monday = wrapper.find('[data-week-day="2026-09-28"]');
    await monday.trigger("dragover");
    await monday.trigger("drop");
    await flushPromises();
    expect(useConfirmState().pending.value).not.toBeNull();
    answerConfirm(false);
    await flushPromises();
    expect(call).not.toHaveBeenCalled();
  });

  it("soltar no próprio dia (ou num dia que passou) não pergunta nada", async () => {
    const wrapper = await mount(PreordersPage);
    await wrapper.find('[data-preorder-card="NB-7"]').trigger("dragstart");
    const same = wrapper.find('[data-week-day="2026-09-26"]');
    await same.trigger("dragover");
    expect(same.attributes("data-drop-target")).toBeUndefined();
    await same.trigger("drop");
    await flushPromises();
    expect(useConfirmState().pending.value).toBeNull();
  });

  it("teclado e toque: o menu 'Mudar de dia' do card oferece os mesmos dias e faz o mesmo gesto", async () => {
    const wrapper = await mount(PreordersPage);
    const trigger = wrapper.find('[data-preorder-card="NB-7"] [data-preorder-move-menu]');
    expect(trigger.attributes("aria-label")).toBe("Mudar de dia a encomenda de Ana Souza");
    await trigger.trigger("click");
    await flushPromises();
    const options = [...document.querySelectorAll<HTMLButtonElement>("[data-preorder-move-to]")];
    // Os outros dias da semana na tela, de hoje em diante (o próprio dia fica de fora).
    expect(options.map((o) => o.dataset.preorderMoveTo)).toEqual(week.days.slice(1).map((d) => d.date));
    expect(document.querySelector("[data-preorder-move-other]")?.textContent).toContain("Outra data ou horário");
    options[2]!.click();
    await vi.waitFor(() => expect(useConfirmState().pending.value?.title).toBe("Mudar a encomenda de Ana Souza para ter, 29/09?"));
    answerConfirm(true);
    await flushPromises();
    expect(call).toHaveBeenCalledWith("/api/v1/backstage/orders/NB-7/reschedule/", {
      body: expect.objectContaining({ date: "2026-09-29" }),
    });
  });

  it("o que já está pronto não se arrasta nem tem o menu: a régua do Reagendar recusaria", async () => {
    week.days[0]!.orders[0] = card({ situation: "ready", situation_label: "Pronto" });
    const wrapper = await mount(PreordersPage);
    const ana = wrapper.find('[data-preorder-card="NB-7"]');
    expect(ana.attributes("draggable")).toBeUndefined();
    expect(ana.find("[data-preorder-move-menu]").exists()).toBe(false);
  });

  it("o servidor diz que não pode: o motivo aparece e nada é perguntado", async () => {
    detail.counter.reschedule = { ...detail.counter.reschedule, allowed: false, block_reason: "A encomenda já entrou no preparo." };
    const wrapper = await mount(PreordersPage);
    await wrapper.find('[data-preorder-card="NB-7"]').trigger("dragstart");
    const monday = wrapper.find('[data-week-day="2026-09-28"]');
    await monday.trigger("dragover");
    await monday.trigger("drop");
    await flushPromises();
    expect(useConfirmState().pending.value).toBeNull();
    expect(call).not.toHaveBeenCalled();
  });
});
