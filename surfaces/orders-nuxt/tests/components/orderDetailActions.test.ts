import { describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import type { CustomerProfileProjection, OperatorOrderProjection } from "../../app/types/orders";

// O detalhe do pedido oferecia ação INVÁLIDA em posição primária: a guarda do
// "Avançar" era `order.can_settle_delivery_cash !== undefined`, que é sempre
// verdadeira, e o "Aceitar" não tinha guarda nenhuma. Num pedido `new` os dois
// apareciam preenchidos e o clique levava 400 do servidor. O board já lia
// `can_advance`/`advance_block_reason`; o detalhe ignorava (a projection do
// detalhe nem os expunha).
//
// Este teste monta a PÁGINA porque quem decide o que o operador pode clicar é
// ela: testar a projection provaria só que os campos existem, não que a tela
// deixou de oferecer o botão.

const detalhe = ref<OperatorOrderProjection | null>(null);
const resendPaymentLink = vi.fn();

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useRoute", () => ({ params: { ref: "WEB-1" } }));
vi.stubGlobal("useOrderEvents", () => {});
vi.stubGlobal("useStationLock", () => ({ denied: ref(false) }));
vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
vi.stubGlobal("useOrderDetail", () => ({
  order: computed(() => detalhe.value),
  pending: ref(false),
  error: ref(null),
  refresh: vi.fn(),
  busy: ref(false),
  confirm: vi.fn(),
  advance: vi.fn(),
  reject: vi.fn(),
  cancel: vi.fn(),
  fetchCancellationReasons: vi.fn(async () => []),
  settleCash: vi.fn(),
  equipmentBack: vi.fn(),
  requeueFiscal: vi.fn(),
  resendPaymentLink: resendPaymentLink,
  saveNotes: vi.fn(),
  addComment: vi.fn(),
  courierDispatch: vi.fn(),
  courierCancel: vi.fn(),
  courierQuote: vi.fn(),
}));

const { default: OrderDetailPage } = await import("../../app/pages/[ref].vue");

function order(over: Partial<OperatorOrderProjection> = {}): OperatorOrderProjection {
  return {
    ref: "WEB-20260625-0007",
    status: "new",
    status_label: "Novo",
    status_color: "",
    customer_name: "Ana",
    channel_ref: "web",
    channel_icon: "language",
    fulfillment_label: "Retirada",
    fulfillment_type: "pickup",
    delivery_address: "",
    delivery_instructions: "",
    total_display: "R$ 15,00",
    items: [{ sku: "PAO", name: "Pão francês", qty: 2, unit_price_display: "R$ 1,00", total_display: "R$ 2,00" }],
    timeline: [],
    kitchen_note: "",
    customer_note: "",
    payment_method: "cash",
    payment_method_label: "Dinheiro",
    payment_status: "pending",
    can_confirm: true,
    can_advance: false,
    next_action_label: "",
    advance_block_label: "",
    advance_block_reason: "",
    can_settle_delivery_cash: false,
    fiscal_status_label: "",
    fiscal_status: "",
    fiscal_links: [],
    awaiting_work_orders: [],
    is_gift: false,
    gift_recipient_name: "",
    gift_recipient_phone: "",
    gift_message: "",
    gift_hide_values: false,
    cancellation_presets: [],
    kitchen_note_tags: [],
    equipment_options: [],
    equipment_out: [],
    equipment_label: "",
    equipment_back_pending: false,
    can_resend_payment_link: false,
    payment_link_notice: "",
    customer_profile: null,
    ...over,
  } as OperatorOrderProjection;
}

/** Perfil do cliente com tudo vazio — cada teste liga só o que quer provar.
 *  O padrão é o vazio de propósito: sem insight (estado NORMAL, não há cron de
 *  recalculate_all) o servidor manda string vazia, nunca zero. */
function profile(over: Partial<CustomerProfileProjection> = {}): CustomerProfileProjection {
  return {
    is_first_order: false,
    total_orders: 0,
    orders_label: "",
    last_order_display: "",
    average_ticket_display: "",
    favorite_product: "",
    segment: "",
    segment_label: "",
    segment_tone: "",
    notes: "",
    dietary_restrictions: "",
    birthday_display: "",
    is_birthday_today: false,
    ...over,
  };
}

const stubs = {
  Icon: true,
  NuxtLink: { template: "<a><slot /></a>" },
  OrderCourierPanel: true,
  OrderReasonDialog: true,
  UiDialog: { template: "<div><slot /></div>" },
  UiDialogContent: { template: "<div><slot /></div>" },
  UiDialogHeader: { template: "<div><slot /></div>" },
  UiDialogTitle: { template: "<div><slot /></div>" },
  UiDialogDescription: { template: "<div><slot /></div>" },
  UiDialogFooter: { template: "<div><slot /></div>" },
};

function abrir(projection: OperatorOrderProjection) {
  detalhe.value = projection;
  return mount(OrderDetailPage, { global: { stubs, mocks: { $router: { go: vi.fn() } } } });
}

describe("detalhe do pedido — só oferece o que o servidor aceita", () => {
  it("pedido novo: oferece Aceitar e Recusar, nunca Avançar", () => {
    const w = abrir(order({ status: "new", can_confirm: true, can_advance: false }));

    // Controle positivo: a página renderizou de fato.
    expect(w.text()).toContain("Ana");
    expect(w.find('[data-action="confirm"]').exists()).toBe(true);
    expect(w.find('[data-action="reject"]').exists()).toBe(true);
    expect(w.find('[data-action="advance"]').exists()).toBe(false);
  });

  it("pedido já aceito: o botão primário é o próximo passo, com o rótulo do servidor", () => {
    const w = abrir(order({
      status: "accepted",
      can_confirm: false,
      can_advance: true,
      next_action_label: "Iniciar preparo",
    }));

    expect(w.find('[data-action="confirm"]').exists()).toBe(false);
    expect(w.find('[data-action="reject"]').exists()).toBe(false);
    expect(w.find('[data-action="advance"]').text()).toContain("Iniciar preparo");
  });

  it("avanço bloqueado: o lugar continua ocupado dizendo o motivo, sem aceitar clique", () => {
    const w = abrir(order({
      status: "preparing",
      can_confirm: false,
      can_advance: false,
      advance_block_label: "Aguardando fornada",
      advance_block_reason: "A fornada do pão francês ainda não terminou.",
    }));

    const bloqueado = w.find('[data-action="advance-blocked"]');
    expect(bloqueado.exists()).toBe(true);
    expect(bloqueado.attributes("disabled")).toBeDefined();
    expect(bloqueado.attributes("title")).toBe("A fornada do pão francês ainda não terminou.");
    expect(w.find('[data-action="advance"]').exists()).toBe(false);
  });

  it("entrega: o endereço aparece na tela de quem despacha", () => {
    const w = abrir(order({
      fulfillment_type: "delivery",
      fulfillment_label: "Entrega",
      delivery_address: "Rua das Flores, 123 - apto 42",
      delivery_instructions: "Portão azul",
    }));

    expect(w.find("[data-order-address]").exists()).toBe(true);
    expect(w.text()).toContain("Rua das Flores, 123 - apto 42");
    expect(w.text()).toContain("Portão azul");
  });

  it("retirada: nenhuma linha de endereço", () => {
    const w = abrir(order({ fulfillment_type: "pickup" }));

    expect(w.text()).toContain("Retirada");
    expect(w.find("[data-order-address]").exists()).toBe(false);
  });
});

describe("detalhe do pedido — observação do cliente (dona diferente da nota da cozinha)", () => {
  it("observação do cliente aparece em bloco próprio, sem invadir o editor da cozinha", () => {
    const w = abrir(order({ customer_note: "Sem cebola, por favor", kitchen_note: "" }));

    const bloco = w.find("[data-customer-note]");
    expect(bloco.exists()).toBe(true);
    expect(bloco.text()).toContain("Observação do cliente");
    expect(bloco.text()).toContain("Sem cebola, por favor");
    // A nota da cozinha continua do operador: o editor não herda o texto do cliente.
    expect((w.find("#order-notes").element as HTMLTextAreaElement).value).toBe("");
  });

  it("sem observação do cliente, o bloco não existe", () => {
    const w = abrir(order({ customer_note: "" }));
    expect(w.find("[data-customer-note]").exists()).toBe(false);
  });
});

describe("detalhe do pedido — presente", () => {
  it("com destinatário: 'Presente para <nome>' + telefone quando houver", () => {
    const w = abrir(order({
      is_gift: true,
      gift_recipient_name: "Maria Silva",
      gift_recipient_phone: "(43) 98888-7777",
    }));

    const bloco = w.find("[data-gift-block]");
    expect(bloco.text()).toContain("Presente para Maria Silva");
    expect(w.find("[data-gift-phone]").text()).toContain("(43) 98888-7777");
  });

  it("presente de retirada sem destinatário: 'Embalar para presente', sem nome pendurado", () => {
    // Caso legítimo (storefront/intents/gift.py): destinatário é opcional na
    // retirada. Antes a tela renderizava "Presente para " no vazio.
    const w = abrir(order({ is_gift: true, gift_recipient_name: "" }));

    const bloco = w.find("[data-gift-block]");
    expect(bloco.exists()).toBe(true);
    expect(bloco.text()).toContain("Embalar para presente");
    expect(bloco.text()).not.toContain("Presente para");
    expect(w.find("[data-gift-phone]").exists()).toBe(false);
  });

  it("gift_hide_values vira instrução visível: 'Não mostrar valores'", () => {
    const w = abrir(order({ is_gift: true, gift_hide_values: true }));
    expect(w.find("[data-gift-hide-values]").text()).toContain("Não mostrar valores");
  });

  it("sem hide_values o selo não aparece", () => {
    const w = abrir(order({ is_gift: true, gift_hide_values: false }));
    expect(w.find("[data-gift-hide-values]").exists()).toBe(false);
  });
});

describe("detalhe do pedido — link de pagamento", () => {
  it("pedido de link cobrável: oferece Reenviar e mostra a prova de envio", async () => {
    resendPaymentLink.mockClear();
    const w = abrir(order({
      status: "accepted",
      can_confirm: false,
      payment_method: "link",
      payment_method_label: "Link de pagamento",
      payment_status: "pending",
      can_resend_payment_link: true,
      payment_link_notice: "Link enviado às 14h32",
    }));

    expect(w.find("[data-payment-link-notice]").text()).toContain("Link enviado às 14h32");
    const botao = w.find('[data-action="resend-payment-link"]');
    expect(botao.exists()).toBe(true);
    expect(botao.text()).toContain("Reenviar link de pagamento");
    await botao.trigger("click");
    expect(resendPaymentLink).toHaveBeenCalledTimes(1);
  });

  it("o servidor negou (pago, vencido, outra forma): nem botão, nem linha vazia", () => {
    const w = abrir(order({ can_resend_payment_link: false, payment_link_notice: "" }));

    expect(w.find('[data-action="resend-payment-link"]').exists()).toBe(false);
    expect(w.find("[data-payment-link-notice]").exists()).toBe(false);
  });

  it("a prova de envio aparece mesmo quando reenviar não dá mais (pedido pago)", () => {
    const w = abrir(order({ can_resend_payment_link: false, payment_link_notice: "Link enviado às 9h05" }));

    expect(w.find("[data-payment-link-notice]").text()).toContain("Link enviado às 9h05");
    expect(w.find('[data-action="resend-payment-link"]').exists()).toBe(false);
  });
});

// O operador abria o detalhe de uma cliente real e não tinha UMA linha sobre
// quem ela era. O dado já estava calculado (CustomerInsight, cadastro,
// histórico) e não chegava aqui. O bloco é de SUPERFÍCIE: o servidor manda os
// fatos em português e só os que sabe; a tela decide onde cada linha mora e
// some com o que faltou — vazio some, não vira " · " solto nem "R$ 0,00".
describe("detalhe do pedido — quem é este cliente", () => {
  it("sem cliente identificado (venda anônima): o bloco não existe", () => {
    const w = abrir(order({ customer_profile: null }));
    expect(w.find("[data-customer-profile]").exists()).toBe(false);
  });

  it("cliente novo: diz 'Primeira compra', sem inventar ticket nem favorito", () => {
    const w = abrir(order({
      customer_profile: profile({ is_first_order: true, orders_label: "Primeira compra" }),
    }));

    const bloco = w.find("[data-customer-profile]");
    expect(bloco.exists()).toBe(true);
    expect(w.find("[data-customer-history]").text()).toBe("Primeira compra");
    expect(w.find("[data-customer-habits]").exists()).toBe(false);
    expect(w.find("[data-customer-segment]").exists()).toBe(false);
  });

  it("cliente de casa: recorrência, recência, ticket e favorito numa leitura só", () => {
    const w = abrir(order({
      customer_profile: profile({
        total_orders: 12,
        orders_label: "12 pedidos",
        last_order_display: "há 12 dias",
        average_ticket_display: "R$ 42,00",
        favorite_product: "Pão francês",
      }),
    }));

    expect(w.find("[data-customer-history]").text()).toBe("12 pedidos · última compra há 12 dias");
    expect(w.find("[data-customer-habits]").text()).toBe("ticket médio R$ 42,00 · costuma levar Pão francês");
  });

  it("fato que falta some da linha, sem deixar separador órfão", () => {
    // O caso do cliente importado: há pedido anterior (a recência é verdade),
    // mas não há insight — sem contagem, sem ticket, sem favorito.
    const w = abrir(order({
      customer_profile: profile({ orders_label: "", last_order_display: "há 3 meses" }),
    }));

    const linha = w.find("[data-customer-history]").text();
    expect(linha).toBe("última compra há 3 meses");
    expect(linha).not.toContain("·");
    expect(w.find("[data-customer-habits]").exists()).toBe(false);
  });

  it("segmento que merece atenção ganha selo; 'regular' não ganha nenhum", () => {
    const fiel = abrir(order({
      customer_profile: profile({ segment: "loyal_customer", segment_label: "Cliente fiel", segment_tone: "success" }),
    }));
    expect(fiel.find("[data-customer-segment]").text()).toBe("Cliente fiel");

    // Regular/recente chegam com tom vazio do servidor — badge que aparece em
    // todo pedido vira moldura, e o operador para de lê-la.
    const regular = abrir(order({
      customer_profile: profile({ segment: "", segment_label: "", segment_tone: "" }),
    }));
    expect(regular.find("[data-customer-segment]").exists()).toBe(false);
  });

  it("restrição alimentar e nota do cadastro aparecem; aniversário só no dia muda o tom", () => {
    const w = abrir(order({
      customer_profile: profile({
        orders_label: "4 pedidos",
        dietary_restrictions: "sem lactose",
        notes: "Prefere retirar no fim da tarde",
        birthday_display: "12/03",
        is_birthday_today: true,
      }),
    }));

    expect(w.find("[data-customer-restrictions]").text()).toContain("sem lactose");
    expect(w.find("[data-customer-notes]").text()).toContain("Prefere retirar no fim da tarde");
    expect(w.find("[data-customer-birthday]").text()).toContain("Faz aniversário hoje");
  });

  it("aniversário fora do dia é só cadastro, com a data", () => {
    const w = abrir(order({
      customer_profile: profile({ birthday_display: "12/03", is_birthday_today: false }),
    }));

    expect(w.find("[data-customer-birthday]").text()).toContain("Aniversário em 12/03");
  });

  it("cadastro sem nada além da recorrência: só a linha que tem fato", () => {
    const w = abrir(order({ customer_profile: profile({ orders_label: "3 pedidos" }) }));

    expect(w.find("[data-customer-profile]").exists()).toBe(true);
    expect(w.find("[data-customer-restrictions]").exists()).toBe(false);
    expect(w.find("[data-customer-notes]").exists()).toBe(false);
    expect(w.find("[data-customer-birthday]").exists()).toBe(false);
  });
});
