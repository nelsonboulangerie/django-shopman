import { fixtureActions } from "../support/orderActions";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { useOrderCashDrafts } from "../../app/composables/useOrderCashDrafts";

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
const requeueFiscal = vi.fn();
const equipmentBack = vi.fn();
const saveNotes = vi.fn();
const confirmFn = vi.fn();
const advanceFn = vi.fn();
const fetchCancellationReasons = vi.fn(async () => []);
// Não retirado (WP-G11): o gesto, o desafio do gerente e a assinatura.
const markNotPickedUp = vi.fn();
const authorize = vi.fn();
const managerChallenge = ref<{ code: string; message: string; action: string } | null>(null);
const readError = ref<unknown>(null);
// Por que a leitura falhou (P1-20): a conta não abre o detalhe, ou o pedido não existe.
const readForbidden = ref(false);
const readNotFound = ref(false);
// A DANFE no detalhe (P1-14): o mesmo gesto do cartão do painel.
const printDanfe = vi.fn();
const danfePrinting = ref(false);
// A impressora desta estação (a Via Pedido sai por ela; P2-19).
const estacao = ref<{ can_print: boolean; agent_url?: string; token?: string; reason: string } | null>(null);

const localStates = new Map<string, ReturnType<typeof ref>>();
beforeEach(() => localStates.clear());
vi.stubGlobal("useState", (key: string, initial: () => unknown) => {
  if (!localStates.has(key)) localStates.set(key, ref(initial()));
  return localStates.get(key);
});
vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { id: 1 } }) }));
vi.stubGlobal("useOrderCashDrafts", useOrderCashDrafts);
vi.stubGlobal("definePageMeta", vi.fn());
vi.stubGlobal("onBeforeRouteLeave", vi.fn());
vi.stubGlobal("useConfirm", () => vi.fn(async () => false));
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
const routeHash = ref("");
vi.stubGlobal("useRoute", () => ({ params: { ref: "WEB-1" }, get hash() { return routeHash.value; } }));
const reveal = vi.fn();
vi.stubGlobal("useNextFocus", () => ({ reveal }));
vi.stubGlobal("useRuntimeConfig", () => ({ public: { adminBaseUrl: "https://api.exemplo" } }));
vi.stubGlobal("useOrderEvents", () => ({ realtime: ref("polling") }));
vi.stubGlobal("useOrdersContext", () => ({ location: ref({ path: "/", query: {} }) }));
vi.stubGlobal("useStationLock", () => ({ denied: ref(false) }));
vi.stubGlobal("useVolumeCheck", () => ({
  state: ref({ conference: null, alarm: null }), check: vi.fn(), switchTo: vi.fn(), dismissAlarm: vi.fn(), end: vi.fn(),
}));
vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
vi.stubGlobal("useNowTick", () => ref(Date.now()));
vi.stubGlobal("useScreen", () => ({ ready: ref(true), belowSm: ref(false), belowMd: ref(false), belowLg: ref(false), belowXl: ref(false) }));
// O widget do iFood sobe na casca (app.vue); o detalhe só lê o estado dele.
const ifoodWidgetState = ref<"off" | "loading" | "ready" | "failed">("off");
beforeEach(() => { ifoodWidgetState.value = "off"; });
const setViewingIFoodOrder = vi.fn();
vi.stubGlobal("useIFoodWidget", () => ({ state: ifoodWidgetState, start: vi.fn(), setViewingIFoodOrder }));
vi.stubGlobal("useOutsideStore", () => ({ askConsent: ref(false), away: ref(false), allow: vi.fn(), decline: vi.fn(), showAll: vi.fn() }));
vi.stubGlobal("useOrderDetail", () => ({
  order: computed(() => detalhe.value),
  deviceAgent: computed(() => estacao.value),
  pending: ref(false),
  error: readError,
  forbidden: readForbidden,
  notFound: readNotFound,
  printDanfe,
  danfePrinting,
  refresh: vi.fn(),
  busy: ref(false),
  confirm: confirmFn,
  advance: advanceFn,
  reject: vi.fn(),
  cancel: vi.fn(),
  fetchCancellationReasons,
  courierBack: vi.fn(async () => true),
  settleCash: vi.fn(),
  equipmentBack,
  requeueFiscal,
  resendPaymentLink: resendPaymentLink,
  saveNotes,
  addComment: vi.fn(),
  courierDispatch: vi.fn(),
  courierCancel: vi.fn(),
  courierQuote: vi.fn(),
  markNotPickedUp,
  authorize,
  managerChallenge,
  dismissManagerChallenge: vi.fn(),
}));

const { default: OrderDetailPage } = await import("../../app/pages/[ref].vue");
const { default: OperatorScreenState } = await import("../../../operator-kit/app/components/OperatorScreenState.vue");

function order(over: Partial<OperatorOrderProjection> = {}): OperatorOrderProjection {
  return {
    ref: "WEB-20260625-0007",
    status: "new",
    status_label: "Novo",
    status_color: "",
    customer_name: "Ana",
    customer_phone: "",
    customer_phone_uri: "",
    customer_whatsapp_url: "",
    customer_email: "",
    customer_ref: "",
    channel_ref: "web",
    channel_icon: "language",
    fulfillment_label: "Retirada",
    fulfillment_type: "pickup",
    delivery_address: "",
    delivery_instructions: "",
    total_display: "R$ 15,00",
    items: [{ sku: "PAO", name: "Pão francês", qty: "2", unit_price_display: "R$ 1,00", total_display: "R$ 2,00" }],
    timeline: [],
    kitchen_note: "",
    customer_note: "",
    payment_method: "cash",
    payment_method_label: "Dinheiro",
    ifood_cancellation_notice: "",
    ifood_payment_summary: [],
    ifood_operation_summary: [],
    ifood_negotiations: [],
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
    cancel_reasons: [],
    kitchen_note_tags: [],
    equipment_options: [],
    equipment_out: [],
    equipment_label: "",
    equipment_back_pending: false,
    dispatch_needs_machine: false,
    trip_with: [],
    courier_return_orders: [],
    courier_return_lines: [],
    can_resend_payment_link: false,
    managers: [{ username: "joyce", name: "Joyce Nogueira" }],
    customer_relay_phone: "",
    customer_relay_code: "",
    customer_relay_expires_at: "",
    payment_link_notice: "",
    customer_profile: null,
    pending: [],
    cancelled_money: null,
    danfe_printable: false,
    danfe_printed: false,
    danfe_state: "",
    danfe_problem: "",
    revisions: {},
    actions: fixtureActions({ can_confirm: true, ...over }),
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
  OperatorCountChip: { props: ["count"], template: "<span data-count>{{ count }}</span>" },
  // O estado da tela entra de verdade: a recusa do detalhe (P1-20) é a frase dele.
  OperatorScreenState,
  // O cabeçalho de uma linha (G14) carrega a ação primária e o ⋯: os slots entram.
  OperatorPageHeader: { template: "<header><slot name='lead' /><slot name='status' /><slot name='actions' /><slot name='phone-actions' /></header>" },
  OperatorLiveStatus: true,
  OperatorRecordNav: true,
  ReadFreshness: true,
  UiIconButton: defineComponent({
    inheritAttrs: false,
    emits: ["click"],
    setup(_, { attrs, emit, slots }) {
      return () => h("button", { ...attrs, type: "button", onClick: (event: MouseEvent) => emit("click", event) }, slots.default?.());
    },
  }),
  NuxtLink: { template: "<a><slot /></a>" },
  OrderCourierPanel: true,
  OrderIFoodNegotiations: true,
  OrderReasonDialog: true,
  OrderNoShowDialog: defineComponent({ name: "OrderNoShowDialog", props: { open: Boolean, orderRef: { type: String, default: "" }, busy: Boolean }, emits: ["update:open", "confirm"], template: "<div />" }),
  OperatorManagerAuth: defineComponent({ name: "OperatorManagerAuth", props: { open: Boolean, action: { type: String, default: "" }, detail: { type: String, default: "" } }, emits: ["update:open", "authorize", "authorize-badge"], template: "<div />" }),
  CourierBackDialog: defineComponent({ name: "CourierBackDialog", props: { card: { type: Object, default: null }, busy: Boolean }, template: "<div />" }),
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

// F4 do laudo do Gestor: o aviso com prazo ("Responder") chega com #ifood-negotiations;
// a página leva o operador à resposta, não só ao pedido.
describe("detalhe do pedido — o aviso leva à negociação iFood", () => {
  beforeEach(() => {
    reveal.mockClear();
    routeHash.value = "";
  });
  const negotiation = { id: "d1", can_respond: true } as unknown as OperatorOrderProjection["ifood_negotiations"][number];
  it("com o destino no endereço e a negociação lida, revela o bloco", async () => {
    routeHash.value = "#ifood-negotiations";
    abrir(order({ ifood_negotiations: [negotiation] }));
    await flushPromises();
    expect(reveal).toHaveBeenCalledWith("ifood-negotiations");
  });
  it("sem o destino no endereço, a página não rola sozinha", async () => {
    abrir(order({ ifood_negotiations: [negotiation] }));
    await flushPromises();
    expect(reveal).not.toHaveBeenCalled();
  });
});

describe("detalhe do pedido — só oferece o que o servidor aceita", () => {
  it("preserva a quantidade fracionária projetada sem arredondar", () => {
    const fractional = order();
    fractional.items[0]!.qty = "0.5";
    const w = abrir(fractional);
    expect(w.text()).toContain("0.5×");
  });
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

  it("encomenda que espera a hora da Cozinha: \"Adiantar\" à vista, nunca como botão principal (WP-G02)", () => {
    const actions = fixtureActions({ can_advance: true, next_action_label: "Adiantar" }).map((action) =>
      action.ref === "advance" ? { ...action, priority: "secondary" } : action,
    );
    const w = abrir(order({
      status: "accepted",
      can_confirm: false,
      can_advance: true,
      next_action_label: "Adiantar",
      kitchen_release_label: "Vai para a Cozinha às 16h15",
      actions,
    }));

    expect(w.find('[data-action="advance"]').exists()).toBe(false);
    expect(w.get('[data-action="advance-secondary"]').text()).toContain("Adiantar");
    expect(w.get("[data-detail-kitchen-wait]").text()).toContain("Vai para a Cozinha às 16h15");
  });

  it("pedido que não espera a Cozinha: nenhum selo de espera", () => {
    const w = abrir(order({ status: "accepted", can_confirm: false, can_advance: true, next_action_label: "Iniciar preparo" }));

    expect(w.find("[data-detail-kitchen-wait]").exists()).toBe(false);
  });

  it("avanço bloqueado: o lugar continua ocupado dizendo o motivo, sem aceitar clique", () => {
    const w = abrir(order({
      status: "preparing",
      can_confirm: false,
      can_advance: false,
      advance_block_label: "Esperando o lote…",
      advance_block_reason: "O lote do pão francês ainda não terminou.",
    }));

    const bloqueado = w.find('[data-action="advance-blocked"]');
    expect(bloqueado.exists()).toBe(true);
    expect(bloqueado.attributes("disabled")).toBeDefined();
    expect(bloqueado.attributes("title")).toBe("O lote do pão francês ainda não terminou.");
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

  it("gift_hide_values vira instrução visível: 'Sem preços no papel'", () => {
    const w = abrir(order({ is_gift: true, gift_hide_values: true }));
    expect(w.find("[data-gift-hide-values]").text()).toContain("Sem preços no papel");
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
    await w.get('[data-action="menu"]').trigger("click");
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

describe("detalhe do pedido — falar com o cliente", () => {
  // Um pedido de cliente real chegou no alpha e o operador, com o detalhe
  // aberto, não tinha como alcançar a pessoa: nem telefone na tela. O dado
  // estava no pedido desde sempre — a projection é que não o publicava.
  it("com telefone: oferece WhatsApp e ligação apontando para o número certo", () => {
    const tela = abrir(
      order({
        customer_phone: "(43) 98123-4567",
        customer_phone_uri: "tel:+5543981234567",
        customer_whatsapp_url: "https://wa.me/5543981234567",
      }),
    );

    expect(tela.find("[data-customer-contact]").exists()).toBe(true);
    expect(tela.find("[data-contact-whatsapp]").attributes("href")).toBe(
      "https://wa.me/5543981234567",
    );
    expect(tela.find("[data-contact-phone]").attributes("href")).toBe("tel:+5543981234567");
    expect(tela.find("[data-customer-phone]").text()).toContain("(43) 98123-4567");
  });

  it("com e-mail: oferece mailto", () => {
    const tela = abrir(order({ customer_email: "cristiane@exemplo.com" }));

    expect(tela.find("[data-contact-email]").attributes("href")).toBe(
      "mailto:cristiane@exemplo.com",
    );
  });

  it("com cadastro: mantém o operador no CRUD de Clientes do Gestor", () => {
    const tela = abrir(order({ customer_ref: "CLI-42" }));

    expect(tela.find("[data-contact-cadastro]").attributes("href")).toBe(
      "/customers/CLI-42",
    );
    expect(tela.find("[data-contact-cadastro]").attributes("target")).toBeUndefined();
  });

  // Botão que não leva a lugar nenhum é pior do que botão nenhum: o operador
  // clica na hora do aperto e não acontece nada.
  it("sem nenhum caminho até a pessoa, o bloco não existe", () => {
    const tela = abrir(order());

    expect(tela.find("[data-customer-contact]").exists()).toBe(false);
  });

  it("telefone anônimo (o nome JÁ é o número) não é repetido ao lado de si mesmo", () => {
    const tela = abrir(
      order({
        customer_name: "(43) 98123-4567",
        customer_phone: "(43) 98123-4567",
        customer_phone_uri: "tel:+5543981234567",
        customer_whatsapp_url: "https://wa.me/5543981234567",
      }),
    );

    expect(tela.find("[data-customer-phone]").exists()).toBe(false);
    expect(tela.find("[data-contact-whatsapp]").exists()).toBe(true);
  });
});


describe("nota da cozinha — atualização concorrente", () => {
  it("SSE preserva texto digitado e exige comparação antes de sobrescrever", async () => {
    const w = abrir(order({ kitchen_note: "Base", revisions: { kitchen_note: "v1" } }));
    await w.get("#order-notes").setValue("Meu rascunho");
    detalhe.value = order({ kitchen_note: "Outra pessoa", revisions: { kitchen_note: "v2" } });
    await w.vm.$nextTick();
    expect((w.get("#order-notes").element as HTMLTextAreaElement).value).toBe("Meu rascunho");
    expect(w.text()).toContain("A nota gravada é: Outra pessoa");
    const save = w.findAll("button").find((button) => button.text() === "Salvar nota")!;
    expect(save.attributes("disabled")).toBeDefined();
    await w.findAll("button").find((button) => button.text() === "Manter meu texto")!.trigger("click");
    expect(save.attributes("disabled")).toBeUndefined();
    expect((w.get("#order-notes").element as HTMLTextAreaElement).value).toBe("Meu rascunho");
    w.unmount();
  });
});


describe("acerto — turno observado no diálogo", () => {
  it("preserva o valor e pede conferência quando o turno muda", async () => {
    const action = (base: string) => ({ ...fixtureActions({ can_confirm: true })[0]!, ref: "settle-delivery-cash",
      payload_schema: { base_revision: base, expected_actor_id: 1 }, confirmation: { description: `Caixa sintético ${base}` } });
    const w = abrir(order({ can_confirm: false, can_settle_delivery_cash: true, actions: [action("turno-1")] }));
    await w.findAll("button").find((button) => button.text().includes("Receber na retirada"))!.trigger("click");
    await w.get('[aria-label="Valor recebido"]').setValue("15,00");
    detalhe.value = order({ can_confirm: false, can_settle_delivery_cash: true, actions: [action("turno-2")] });
    await w.vm.$nextTick();
    expect(w.text()).toContain("O pedido ou turno mudou");
    expect((w.get('[aria-label="Valor recebido"]').element as HTMLInputElement).value).toBe("15,00");
    const confirm = w.findAll("button").find((button) => button.text() === "Confirmar")!;
    expect(confirm.attributes("disabled")).toBeDefined();
    await w.findAll("button").find((button) => button.text() === "Conferir e manter os valores digitados")!.trigger("click");
    expect(confirm.attributes("disabled")).toBeUndefined();
    expect((w.get('[aria-label="Valor recebido"]').element as HTMLInputElement).value).toBe("15,00");
    w.unmount();
  });
});

it("falha de leitura mantém o pedido e o textarea montados junto da explicação", async () => {
  const w = abrir(order({ kitchen_note: "Base", revisions: { kitchen_note: "v1" } }));
  try {
    await w.get("#order-notes").setValue("Texto ainda não salvo");
    const field = w.get("#order-notes").element;
    readError.value = { statusCode: 503 };
    await w.vm.$nextTick();
    expect(w.get("#order-notes").element).toBe(field);
    expect((field as HTMLTextAreaElement).value).toBe("Texto ainda não salvo");
    expect(w.get("[data-order-error]").text()).toContain("Mantivemos a última leitura");
    expect(w.text()).toContain("Ana");
  } finally { readError.value = null; w.unmount(); }
});

it("fechar e reabrir o acerto conserva valor e pede revisar a custódia que mudou", async () => {
  const action = (base: string) => ({ ...fixtureActions({ can_confirm: true })[0]!, ref: "settle-delivery-cash",
    label: "Acertar dinheiro", payload_schema: { base_revision: base }, confirmation: { required: true, description: base } });
  const w = abrir(order({ can_confirm: false, can_settle_delivery_cash: true, actions: [action("turno-1")] }));
  const open = () => w.findAll("button").find(button => button.text().includes("Receber na retirada"))!;
  await open().trigger("click");
  await w.find('[aria-label="Valor recebido"]').setValue("15,00");
  await w.findAll("button").find(button => button.text() === "Voltar")!.trigger("click");
  detalhe.value = order({ can_confirm: false, can_settle_delivery_cash: true, actions: [action("turno-2")] });
  await open().trigger("click");
  expect((w.find('[aria-label="Valor recebido"]').element as HTMLInputElement).value).toBe("15,00");
  expect(w.text()).toContain("O pedido ou turno mudou");
});


it.each([
  ["requeue-fiscal", "Reprocessar NFC-e", { fiscal_status: "failed" }, requeueFiscal],
  ["equipment-back", "Maquininha voltou", { equipment_back_pending: true }, equipmentBack],
] as const)("respects disabled projected recovery %s without a request", async (refName, label, fields, execute) => {
  execute.mockClear();
  const reason = "Esta ação exige outra permissão.";
  const w = abrir(order({ ...fields, can_confirm: false, actions: [{
    ref: refName, kind: "mutation", label, enabled: false, reason, priority: "secondary",
    href: "", method: "POST", idempotency: "required", payload_schema: {}, confirmation: {},
  }] }));
  await w.get('[data-action="menu"]').trigger("click");
  const button = w.findAll("button").find((candidate) => candidate.text().includes(label))!;
  expect(button.attributes("disabled")).toBeDefined();
  expect(button.attributes("title")).toBe(reason);
  await button.trigger("click");
  expect(execute).not.toHaveBeenCalled();
  w.unmount();
});


it("keeps a confirmed note when the following useful read fails", async () => {
  const w = abrir(order({ can_confirm: false, kitchen_note: "Nota anterior", revisions: { kitchen_note: "old-base" } }));
  try {
    saveNotes.mockImplementationOnce(async () => { readError.value = new Error("synthetic read unavailable"); return true; });
    const note = w.find("#order-notes");
    await note.setValue("Nota nova confirmada");
    await w.findAll("button").find((button) => button.text() === "Salvar nota")!.trigger("click");
    await flushPromises();
    expect((note.element as HTMLTextAreaElement).value).toBe("Nota nova confirmada");
  } finally { readError.value = null; w.unmount(); }
});

// Não retirado (WP-G11): quem decide se a porta existe, e se já pode ser tocada, é
// o servidor, pela ação `no-show` de `order.actions`. A tela não repete a régua
// (pronto, de retirada, fora do iFood, a hora): sem a ação, não há item.
describe("detalhe do pedido — não retirado", () => {
  const noShow = (over: Partial<OperatorOrderProjection["actions"][number]> = {}) => ({
    ...fixtureActions({ can_confirm: true })[0]!,
    ref: "no-show",
    label: "Não retirado",
    priority: "menu",
    payload_schema: { base_revision: "detail-base", expected_actor_id: 1 },
    confirmation: { required: true, manager_approval: true },
    ...over,
  });
  const ready = (over: Partial<OperatorOrderProjection> = {}) =>
    order({ status: "ready", status_label: "Pronto", can_confirm: false, actions: [noShow()], ...over });
  const moneySentence = "R$ 12,00 serão estornados ao Pix do cliente. R$ 8,00 ficam com a loja, pelo que se perdeu.";

  beforeEach(() => {
    markNotPickedUp.mockReset();
    authorize.mockReset();
    managerChallenge.value = null;
    vi.mocked(useSonner.success).mockClear();
  });

  it("a ação veio do servidor: o item existe, avisa que pede gerente e abre o diálogo", async () => {
    const w = abrir(ready());
    await w.get('[data-action="menu"]').trigger("click");
    const item = w.get('[data-action="no-show"]');

    expect(item.text()).toContain("Não retirado (pede gerente)");
    expect(item.attributes("disabled")).toBeUndefined();
    expect(w.getComponent({ name: "OrderNoShowDialog" }).props("open")).toBe(false);

    await item.trigger("click");
    const dialog = w.getComponent({ name: "OrderNoShowDialog" });
    expect(dialog.props("open")).toBe(true);
    expect(dialog.props("orderRef")).toBe("WEB-1");
    w.unmount();
  });

  it("antes da hora: o item fica no lugar, desabilitado, com o motivo do servidor à vista", async () => {
    const reason = "Pedido pago: o não retirado libera no corte do dia, às 18h.";
    const w = abrir(ready({ actions: [noShow({ enabled: false, reason })] }));
    await w.get('[data-action="menu"]').trigger("click");
    const item = w.get('[data-action="no-show"]');

    expect(item.attributes("disabled")).toBeDefined();
    expect(item.attributes("title")).toBe(reason);
    expect(item.text()).toContain(reason);
    await item.trigger("click");
    expect(w.getComponent({ name: "OrderNoShowDialog" }).props("open")).toBe(false);
    w.unmount();
  });

  it("pedido sem a ação (iFood, entrega, ainda não pronto): o item não existe", async () => {
    const semAcao = [
      order({ status: "ready", can_confirm: false, channel_ref: "ifood", actions: [] }),
      order({ status: "ready", can_confirm: false, fulfillment_type: "delivery", actions: [] }),
      order({ status: "new" }),
    ];
    for (const projection of semAcao) {
      const w = abrir(projection);
      await w.get('[data-action="menu"]').trigger("click");
      expect(w.find('[data-action="no-show"]').exists()).toBe(false);
      w.unmount();
    }
  });

  it("confirmar leva a ação da PRÉVIA; o gerente lê a frase do dinheiro e, assinado, o diálogo fecha", async () => {
    const contract = noShow({ label: "Encerrar como não retirado", priority: "danger", payload_schema: { base_revision: "preview-base", expected_actor_id: 1 } });
    // O servidor pede o gerente: o gesto volta `false` e o desafio sobe.
    markNotPickedUp.mockImplementationOnce(async () => {
      managerChallenge.value = { code: "manager_approval_required", message: "Não retirado pede a autorização de um gerente.", action: "no-show" };
      return false;
    });
    authorize.mockImplementationOnce(async () => {
      managerChallenge.value = null;
      return true;
    });
    const w = abrir(ready());
    await w.get('[data-action="menu"]').trigger("click");
    await w.get('[data-action="no-show"]').trigger("click");

    w.getComponent({ name: "OrderNoShowDialog" }).vm.$emit("confirm", { contract, moneySentence });
    await flushPromises();
    expect(markNotPickedUp).toHaveBeenCalledWith(contract);
    const auth = w.getComponent({ name: "OperatorManagerAuth" });
    expect(auth.props("open")).toBe(true);
    expect(auth.props("action")).toBe("order_no_show");
    expect(auth.props("detail")).toBe(moneySentence);
    // O diálogo do gesto continua por baixo da assinatura.
    expect(w.getComponent({ name: "OrderNoShowDialog" }).props("open")).toBe(true);

    auth.vm.$emit("authorize", "joyce", "1234");
    await flushPromises();
    expect(authorize).toHaveBeenCalledWith({ username: "joyce", pin: "1234" });
    expect(w.getComponent({ name: "OrderNoShowDialog" }).props("open")).toBe(false);
    expect(useSonner.success).toHaveBeenCalledWith("Pedido encerrado como não retirado.");
    w.unmount();
  });

  it("PIN recusado: o diálogo do gesto continua aberto e nada é dado como feito", async () => {
    markNotPickedUp.mockImplementationOnce(async () => {
      managerChallenge.value = { code: "manager_approval_required", message: "", action: "no-show" };
      return false;
    });
    authorize.mockResolvedValueOnce(false);
    const w = abrir(ready());
    await w.get('[data-action="menu"]').trigger("click");
    await w.get('[data-action="no-show"]').trigger("click");
    w.getComponent({ name: "OrderNoShowDialog" }).vm.$emit("confirm", { contract: noShow(), moneySentence });
    await flushPromises();

    w.getComponent({ name: "OperatorManagerAuth" }).vm.$emit("authorize", "joyce", "0000");
    await flushPromises();
    expect(w.getComponent({ name: "OrderNoShowDialog" }).props("open")).toBe(true);
    expect(useSonner.success).not.toHaveBeenCalled();
    w.unmount();
  });

  it("o cancelamento de pedido pago segue com o ato e o motivo dele", async () => {
    managerChallenge.value = { code: "manager_approval_required", message: "", action: "cancel" };
    const w = abrir(ready({ cancel_money_effect: "R$ 5,10 serão estornados no cartão do cliente." } as Partial<OperatorOrderProjection>));
    const auth = w.getComponent({ name: "OperatorManagerAuth" });
    expect(auth.props("action")).toBe("cancel_order");
    expect(auth.props("detail")).toBe("R$ 5,10 serão estornados no cartão do cliente.");
    w.unmount();
  });
});

// Beta 06/11: o atalho "Bem assado" só preenchia o rascunho; o operador tocou
// Aceitar sem ver o "Salvar nota" e o ticket da Cozinha saiu sem a nota.
describe("nota da cozinha vai junto com o gesto do momento", () => {
  beforeEach(() => {
    saveNotes.mockReset();
    confirmFn.mockReset();
    advanceFn.mockReset();
  });
  const tocarAtalho = async (w: ReturnType<typeof abrir>, tag: string) =>
    w.findAll("button").find((button) => button.text() === tag)!.trigger("click");

  it("Aceitar com o atalho no rascunho grava a nota ANTES de aceitar", async () => {
    const calls: string[] = [];
    saveNotes.mockImplementation(async (text: string) => {
      calls.push(`notes:${text}`);
      detalhe.value = { ...detalhe.value!, kitchen_note: text };
      return true;
    });
    confirmFn.mockImplementation(() => { calls.push("confirm"); });
    const w = abrir(order({ kitchen_note_tags: ["Bem assado"] }));
    await tocarAtalho(w, "Bem assado");
    await w.get('[data-action="confirm"]').trigger("click");
    await flushPromises();
    expect(calls).toEqual(["notes:Bem assado", "confirm"]);
    expect(w.findAll("button").some((button) => button.text() === "Salvar nota")).toBe(false);
    w.unmount();
  });

  it("Avançar também leva o texto digitado", async () => {
    saveNotes.mockImplementation(async (text: string) => {
      detalhe.value = { ...detalhe.value!, kitchen_note: text };
      return true;
    });
    const w = abrir(order({ status: "accepted", can_confirm: false, can_advance: true, next_action_label: "Iniciar preparo" }));
    await w.get("#order-notes").setValue("Sem gergelim");
    await w.get('[data-action="advance"]').trigger("click");
    await flushPromises();
    expect(saveNotes).toHaveBeenCalledWith("Sem gergelim", "");
    expect(advanceFn).toHaveBeenCalledTimes(1);
    w.unmount();
  });

  it("se a nota não grava, o pedido NÃO é aceito e o rascunho fica", async () => {
    saveNotes.mockImplementation(async () => false);
    const w = abrir(order({ kitchen_note_tags: ["Bem assado"] }));
    await tocarAtalho(w, "Bem assado");
    await w.get('[data-action="confirm"]').trigger("click");
    await flushPromises();
    expect(confirmFn).not.toHaveBeenCalled();
    expect((w.get("#order-notes").element as HTMLTextAreaElement).value).toBe("Bem assado");
    w.unmount();
  });

  it("sem rascunho, Aceitar não grava nota nenhuma", async () => {
    const w = abrir(order({ kitchen_note: "Bem assado" }));
    await w.get('[data-action="confirm"]').trigger("click");
    await flushPromises();
    expect(saveNotes).not.toHaveBeenCalled();
    expect(confirmFn).toHaveBeenCalledTimes(1);
    w.unmount();
  });
});

describe("detalhe iFood", () => {
  it("mostra o aviso de cancelamento pendente e os valores a cobrar sem liberar avanço", () => {
    const notice = "Cancelamento solicitado ao iFood. Aguardando confirmação.";
    const w = abrir(order({
      channel_ref: "ifood", status: "accepted", status_label: "Confirmado",
      can_confirm: false, can_advance: false,
      advance_block_label: "Aguardando iFood", advance_block_reason: notice,
      ifood_cancellation_notice: notice,
      ifood_payment_summary: ["Cobrar na entrega: R$ 15,00"],
    }));
    expect(w.get("[data-ifood-cancellation]").text()).toBe(notice);
    expect(w.get("[data-ifood-payment]").text()).toBe("Cobrar na entrega: R$ 15,00");
    expect(w.get('[data-action="advance-blocked"]').attributes("disabled")).toBeDefined();
    expect(w.find('[data-action="advance"]').exists()).toBe(false);
    expect(w.text()).toContain("Confirmado");
  });
});

describe("chat do cliente iFood (widget do iFood, DEV-2026-019)", () => {
  it("pedido do iFood com o widget pronto: diz que o chat está no botão do iFood", () => {
    ifoodWidgetState.value = "ready";
    const w = abrir(order({ channel_ref: "ifood" }));
    expect(w.get("[data-ifood-chat]").attributes("data-ifood-chat-state")).toBe("ready");
    expect(w.get("[data-ifood-chat]").text()).toContain("botão do iFood");
  });

  it("o widget não carregou: manda responder pelo Gestor do iFood", () => {
    ifoodWidgetState.value = "failed";
    const w = abrir(order({ channel_ref: "ifood" }));
    expect(w.get("[data-ifood-chat]").text()).toContain("Gestor do iFood");
  });

  it("o detalhe de pedido iFood avisa que o botão do iFood deve aparecer; o de outro canal, não", () => {
    setViewingIFoodOrder.mockClear();
    abrir(order({ channel_ref: "ifood" })).unmount();
    expect(setViewingIFoodOrder.mock.calls.map((c) => c[0])).toEqual([true, false]);
    setViewingIFoodOrder.mockClear();
    abrir(order({ channel_ref: "web" }));
    expect(setViewingIFoodOrder).toHaveBeenCalledWith(false);
    expect(setViewingIFoodOrder).not.toHaveBeenCalledWith(true);
  });

  it("widget desligado na loja, ou pedido de outro canal: nada aparece", () => {
    expect(abrir(order({ channel_ref: "ifood" })).find("[data-ifood-chat]").exists()).toBe(false);
    ifoodWidgetState.value = "ready";
    expect(abrir(order({ channel_ref: "web" })).find("[data-ifood-chat]").exists()).toBe(false);
  });
});

describe("segunda assinatura no cancelamento", () => {
  // 21/09: cancelando pedido do iFood com o prazo correndo, o diálogo caía no
  // campo livre e o gerente tinha de digitar o próprio nome. No PDV ele já era
  // selecionado; o Gestor não recebia a lista.
  it("entrega ao diálogo a lista de gerentes, para selecionar em vez de digitar", () => {
    const ManagerAuthStub = defineComponent({
      name: "OperatorManagerAuth",
      props: { open: Boolean, managers: { type: Array, default: () => [] }, action: String, busy: Boolean, error: String },
      template: "<div data-manager-auth />",
    });
    detalhe.value = order({ managers: [{ username: "joyce", name: "Joyce Nogueira" }] });
    const w = mount(OrderDetailPage, { global: { stubs: { ...stubs, OperatorManagerAuth: ManagerAuthStub }, mocks: { $router: { go: vi.fn() } } } });

    expect(w.findComponent(ManagerAuthStub).props("managers")).toEqual([{ username: "joyce", name: "Joyce Nogueira" }]);
  });
});

describe("contato de pedido do iFood", () => {
  // 21/09: o detalhe oferecia WhatsApp para o 0800 da central do iFood.
  // 12/11/2026: a central vira rodapé pró-forma, um link discreto, sem botão.
  it("relé mostra a central e o código no rodapé, sem WhatsApp", () => {
    const w = abrir(order({
      customer_phone: "", customer_whatsapp_url: "",
      customer_phone_uri: "tel:08007053040,89338721",
      customer_relay_phone: "0800 705 3040", customer_relay_code: "89338721",
    }));
    expect(w.find("[data-contact-whatsapp]").exists()).toBe(false);
    expect(w.get("[data-contact-relay-code]").text()).toBe("89338721");
    expect(w.get("[data-contact-relay] [data-contact-phone]").text()).toBe("0800 705 3040");
    expect(w.get("[data-contact-relay] [data-contact-phone]").attributes("href")).toBe("tel:08007053040,89338721");
  });
  it("código vencido diz que a central não repassa e não oferece ligação", () => {
    const w = abrir(order({
      customer_phone: "", customer_whatsapp_url: "", customer_phone_uri: "",
      customer_relay_phone: "0800 705 3040", customer_relay_code: "",
    }));
    expect(w.find("[data-contact-phone]").exists()).toBe(false);
    expect(w.get("[data-contact-relay-expired]").text()).toContain("o código venceu");
  });
});

describe("G14: o detalhe em duas colunas com a ação primária no cabeçalho", () => {
  it("cabeçalho de uma linha leva Aceitar e Recusar; Cancelar mora no ⋯", async () => {
    const w = abrir(order({ can_cancel: true }));
    expect(w.get("[data-order-detail]").attributes("data-order-layout")).toBe("split");
    expect(w.get("header [data-action='confirm']").text()).toContain("Aceitar");
    expect(w.find("header [data-action='reject']").exists()).toBe(true);
    expect(w.find("[data-action='cancel']").exists()).toBe(false);
    await w.get("[data-action='menu']").trigger("click");
    expect(w.get("[data-detail-menu] [data-action='cancel']").text()).toContain("Cancelar pedido");
    w.unmount();
  });

  // P2-19: o Gestor imprime a Via Pedido do PDV, do ⋯ do detalhe.
  it("o ⋯ oferece Imprimir Via Pedido; sem impressora, apagado e dizendo por quê", async () => {
    estacao.value = { can_print: false, reason: "Este dispositivo não tem impressora configurada." };
    const w = abrir(order());
    await w.get("[data-action='menu']").trigger("click");
    const item = w.get("[data-detail-menu] [data-action='order-ticket']");
    expect(item.text()).toContain("Imprimir Via Pedido");
    expect(item.text()).toContain("Este dispositivo não tem impressora.");
    expect(item.attributes("disabled")).toBeDefined();
    w.unmount();

    estacao.value = { can_print: true, agent_url: "http://127.0.0.1:9123", token: "t", reason: "" };
    const comImpressora = abrir(order());
    await comImpressora.get("[data-action='menu']").trigger("click");
    expect(
      comImpressora.get("[data-detail-menu] [data-action='order-ticket']").attributes("disabled"),
    ).toBeUndefined();
    comImpressora.unmount();
    estacao.value = null;
  });
});

// Beta test de 05/11/2026 (frente gestor-pedidos).
describe("detalhe do pedido: achados do beta 05/11", () => {
  const mutation = (ref: string, label: string, over: Record<string, unknown> = {}) => ({
    ref, label, enabled: true, reason: "", priority: "primary", kind: "mutation", href: "", method: "POST",
    payload_schema: { expected_actor_id: 1, base_revision: "b" }, idempotency: "required", confirmation: {}, ...over,
  });
  beforeEach(() => {
    routeHash.value = "";
    fetchCancellationReasons.mockClear();
  });

  // GES-10 / GES-15: pedido cancelado continuava com a nota da cozinha editável.
  it("pedido encerrado: a nota da cozinha não tem editor", () => {
    const w = abrir(order({
      status: "cancelled", can_confirm: false, kitchen_note: "Bem assado",
      actions: [mutation("notes", "Salvar nota", { enabled: false, reason: "Pedido encerrado." })] as never,
    }));
    expect(w.find("#order-notes").exists()).toBe(false);
    expect(w.text()).toContain("Bem assado");
    w.unmount();
  });

  // Com o iFood (ou a Cozinha) conduzindo, o pronto vem como "menu": do md para cima
  // ele fica à vista, secundário, em vez de escondido no ⋯ (dono, 14/11/2026).
  it("pronto que não é o gesto do momento fica à vista no desktop", async () => {
    const w = abrir(order({
      status: "preparing", channel_ref: "ifood", can_confirm: false,
      actions: [mutation("advance", "Marcar pronto", { priority: "menu" })] as never,
    }));
    expect(w.get('[data-action="advance-secondary"]').text()).toContain("Marcar pronto");
    await w.get('[data-action="menu"]').trigger("click");
    expect(w.find("[data-detail-menu] [data-action='advance']").exists()).toBe(false);
    w.unmount();
  });

  // GES-12: o detalhe dizia "Marcar como entregue" e escondia troco e maquininha.
  it("na rua com troco: o gesto é Entregador voltou e a custódia aparece", async () => {
    const w = abrir(order({
      status: "dispatched", fulfillment_type: "delivery", can_confirm: false,
      change_label: "Entregador levou R$ 26,00 de troco", equipment_label: "Saiu com a maquininha de demonstração",
      courier_return_lines: ["R$ 50,00 em dinheiro"], courier_return_orders: ["WEB-20260625-0007"],
      actions: [mutation("advance", "Marcar como entregue"), mutation("courier-back", "Entregador voltou", { confirmation: { required: true } })] as never,
    }));
    expect(w.get('[data-action="courier-back"]').text()).toContain("Entregador voltou");
    expect(w.get("[data-detail-custody]").text()).toContain("Entregador levou R$ 26,00 de troco");
    expect(w.get("[data-detail-custody]").text()).toContain("Saiu com a maquininha de demonstração");
    await w.get('[data-action="courier-back"]').trigger("click");
    await flushPromises();
    const dialog = w.findComponent({ name: "CourierBackDialog" });
    expect(dialog.props("card")).toMatchObject({ courier_return_lines: ["R$ 50,00 em dinheiro"] });
    // Com espaço (md+), o "Marcar como entregue" fica à vista ao lado do primário, e não
    // escondido no ⋯ (dono, 14/11/2026).
    const secondary = w.get('[data-action="advance-secondary"]');
    expect(secondary.text()).toContain("Marcar como entregue");
    expect(secondary.attributes("title")).toBe("O que saiu com o entregador continua em aberto.");
    await w.get('[data-action="menu"]').trigger("click");
    expect(w.find("[data-detail-menu] [data-action='advance']").exists()).toBe(false);
    w.unmount();
  });

  // GES-05 / GES-16: Pix vencido tinha só o botão morto; cancelar exigia achar o ⋯.
  // WP-G05 (P1-16): o fato é um só e mora na faixa "O que falta", com o gesto ao lado.
  it("Pix vencido: a faixa do que falta traz Cancelar com o motivo já marcado", async () => {
    const w = abrir(order({
      status: "accepted", can_confirm: false, can_cancel: true, payment_lapsed: true,
      advance_block_label: "Pix expirado", advance_block_reason: "gerado às 05h51 · expirou às 05h57",
      pending: [{
        key: "payment", tone: "error", label: "Pix expirado", reason: "Gerado às 05h51 · expirou às 05h57.",
        actions: [{ ref: "cancel", label: "Cancelar pedido", enabled: true, reason: "", href: "" }],
      }],
    }));
    // Um fato só: o aviso de bloqueio em vermelho deixou de existir à parte.
    expect(w.findAll("[data-detail-block]")).toHaveLength(1);
    expect(w.get('[data-pending="payment"]').text()).toContain("Pix expirado");
    await w.get('[data-pending-action="cancel"]').trigger("click");
    await flushPromises();
    expect(w.get("order-reason-dialog-stub").attributes("initial-key")).toBe("payment_not_confirmed");
    // Loja online: não há lista viva de códigos para buscar (GES-06).
    expect(fetchCancellationReasons).not.toHaveBeenCalled();
    w.unmount();
  });

  it("o cartão da Fila chega com #cancel-unpaid e o cancelar já abre", async () => {
    routeHash.value = "#cancel-unpaid";
    const w = abrir(order({
      status: "accepted", can_confirm: false, can_cancel: true, payment_lapsed: true,
      advance_block_label: "Pix expirado", advance_block_reason: "expirou às 05:57",
    }));
    await flushPromises();
    expect(w.get("order-reason-dialog-stub").attributes("open")).toBe("true");
    w.unmount();
  });
});


describe("atalhos gerais da nota do pedido", () => {
  it("explica o escopo sem inferir etiquetas pelo produto nem alterar o cadastro", () => {
    const tags = ["Bem assado", "Pouco assado"];
    const w = abrir(order({ kitchen_note_tags: tags }));
    // P2-28: o rótulo diz o que o toque faz; a instrução ao operador saiu.
    expect(w.get("[data-kitchen-note-tags-scope]").text()).toBe("Acrescentar à nota:");
    expect(w.text()).not.toContain("Use apenas os que se aplicam");
    expect(w.text()).not.toContain("KDS");
    expect(w.text()).toContain("Aparece no ticket deste pedido, na tela da Cozinha.");
    expect(w.findAll("button").some(b => b.text() === "Bem assado")).toBe(true);
    expect(detalhe.value?.kitchen_note_tags).toEqual(tags);
    w.unmount();
  });
  it("sem atalhos cadastrados, não explica uma lista inexistente", () => {
    const w = abrir(order({ kitchen_note_tags: [] }));
    expect(w.find("[data-kitchen-note-tags-scope]").exists()).toBe(false);
    w.unmount();
  });
});


// WP-G05: o detalhe abre com "O que falta neste pedido", e cada linha tem o gesto que a
// página já sabia fazer. A faixa só aponta: quem decide o que falta é o servidor.
describe("detalhe do pedido — o que falta, com o gesto ao lado", () => {
  const line = (over: Partial<OperatorOrderProjection["pending"][number]>) => ({
    key: "nfce", tone: "error", label: "NFC-e não autorizada", reason: "", actions: [], ...over,
  });
  const gesture = (ref: string, label: string, over: Record<string, unknown> = {}) => ({
    ref, label, enabled: true, reason: "", href: "", ...over,
  });
  beforeEach(() => {
    requeueFiscal.mockClear();
    resendPaymentLink.mockClear();
    printDanfe.mockClear();
    danfePrinting.value = false;
  });

  it("sem pendência e sem dinheiro de cancelado, a faixa não existe", () => {
    const w = abrir(order({ can_confirm: false }));
    expect(w.find("[data-order-pending]").exists()).toBe(false);
    w.unmount();
  });

  it("a nota recusada traz a resposta do emissor e o Reprocessar na própria linha (P1-13)", async () => {
    const w = abrir(order({
      status: "ready", can_confirm: false, fiscal_status: "failed", fiscal_status_label: "NFC-e não autorizada",
      pending: [line({
        reason: "Resposta do emissor: Rejeição 778: NCM inexistente. Se reprocessar não resolver, chame o contador.",
        actions: [gesture("requeue-fiscal", "Reprocessar NFC-e")],
      })],
    }));
    const row = w.get('[data-pending="nfce"]');
    expect(row.attributes("data-pending-tone")).toBe("error");
    expect(row.text()).toContain("Rejeição 778: NCM inexistente");
    await w.get('[data-pending-action="requeue-fiscal"]').trigger("click");
    expect(requeueFiscal).toHaveBeenCalledTimes(1);
    w.unmount();
  });

  it("a DANFE que não saiu se imprime da faixa, e o ⋯ do pedido também imprime (P1-14)", async () => {
    const w = abrir(order({
      status: "dispatched", can_confirm: false, fulfillment_type: "delivery",
      danfe_printable: true, danfe_printed: false, danfe_state: "not_printed",
      danfe_problem: "A impressora de Balcão não buscou a DANFE. Confira se o computador dela está ligado.",
      pending: [line({
        key: "danfe", tone: "warning", label: "DANFE não impressa",
        reason: "A impressora de Balcão não buscou a DANFE. Confira se o computador dela está ligado.",
        actions: [gesture("print-danfe", "Imprimir DANFE")],
      })],
    }));
    await w.get('[data-pending-action="print-danfe"]').trigger("click");
    expect(printDanfe).toHaveBeenCalledTimes(1);
    await w.get('[data-action="menu"]').trigger("click");
    const item = w.findAll("button").find((button) => button.text().includes("Imprimir DANFE") && !button.attributes("data-pending-action"))!;
    await item.trigger("click");
    expect(printDanfe).toHaveBeenCalledTimes(2);
    w.unmount();
  });

  it("DANFE já impressa: o ⋯ do pedido oferece Reimprimir, sem linha na faixa", async () => {
    const w = abrir(order({
      status: "ready", can_confirm: false, danfe_printable: true, danfe_printed: true, danfe_state: "printed",
    }));
    expect(w.find("[data-order-pending]").exists()).toBe(false);
    await w.get('[data-action="menu"]').trigger("click");
    expect(w.findAll("button").some((button) => button.text().includes("Reimprimir DANFE"))).toBe(true);
    w.unmount();
  });

  it("sem nota, o ⋯ do pedido não oferece DANFE", async () => {
    const w = abrir(order({ status: "ready", can_confirm: false }));
    await w.get('[data-action="menu"]').trigger("click");
    expect(w.findAll("button").some((button) => button.text().includes("DANFE"))).toBe(false);
    w.unmount();
  });

  it("o link que pode não ter chegado se reenvia da faixa", async () => {
    const w = abrir(order({
      status: "accepted", can_confirm: false, payment_method: "link",
      pending: [line({
        key: "payment", tone: "warning", label: "Aguardando pagamento", reason: "O envio do link falhou. Reenvie o link.",
        actions: [gesture("resend-payment-link", "Reenviar link de pagamento")],
      })],
    }));
    await w.get('[data-pending-action="resend-payment-link"]').trigger("click");
    expect(resendPaymentLink).toHaveBeenCalledTimes(1);
    w.unmount();
  });

  it("espera saudável: sem cor de erro, e o botão travado guarda o nome do gesto (P2-26)", () => {
    // Como o servidor manda: a ação travada guarda o nome do gesto, e o motivo vai em `reason`.
    const actions = fixtureActions({ can_advance: true, next_action_label: "Iniciar preparo" }).map((action) =>
      action.ref === "advance"
        ? { ...action, enabled: false, reason: "Encomenda para uma data futura. O preparo abre no dia combinado." }
        : action,
    );
    const w = abrir(order({
      status: "accepted", can_confirm: false, can_advance: false, actions,
      advance_block_label: "Aguardando o dia da encomenda…",
      advance_block_reason: "Encomenda para uma data futura. O preparo abre no dia combinado.",
      pending: [line({
        key: "advance", tone: "info", label: "Aguardando o dia da encomenda",
        reason: "Combinado: Amanhã · 08h às 10h. O preparo abre nesse dia.",
      })],
    }));
    const row = w.get('[data-pending="advance"]');
    expect(row.attributes("data-pending-tone")).toBe("info");
    expect(row.text()).toContain("Combinado: Amanhã · 08h às 10h");
    // O fato não se repete no rótulo do botão principal.
    const blocked = w.get('[data-action="advance-blocked"]');
    expect(blocked.text()).toContain("Iniciar preparo");
    expect(blocked.text()).not.toContain("Aguardando");
    expect(blocked.attributes("disabled")).toBeDefined();
    w.unmount();
  });

  it("cancelado com estorno pedido, e depois estornado, com a frase que o cliente lê (P1-15, P2-25)", async () => {
    const w = abrir(order({
      status: "cancelled", can_confirm: false, payment_method_label: "Pix", payment_status_label: "Estorno pedido",
      cancelled_money: { state: "refund_requested", label: "Estorno pedido", amount_display: "R$ 18,70", customer_line: "Estamos devolvendo os R$ 18,70 do seu Pix para a mesma conta.", settled: false },
      pending: [line({
        key: "refund", tone: "info", label: "Estorno pedido",
        reason: "A devolução de R$ 18,70 foi pedida e ainda não foi confirmada. O cliente lê na loja: “Estamos devolvendo os R$ 18,70 do seu Pix para a mesma conta.”",
      })],
      actions: [],
    }));
    expect(w.get('[data-pending="refund"]').text()).toContain("Estorno pedido");
    expect(w.get('[data-pending="refund"]').text()).toContain("Estamos devolvendo os R$ 18,70 do seu Pix para a mesma conta.");
    expect(w.find("[data-order-money]").exists()).toBe(false);

    detalhe.value = order({
      status: "cancelled", can_confirm: false, payment_method_label: "Pix", payment_status_label: "Estornado",
      cancelled_money: { state: "refunded", label: "Estornado", amount_display: "R$ 18,70", customer_line: "Devolvemos os R$ 18,70 do seu Pix para a mesma conta.", settled: true },
      pending: [], actions: [],
    });
    await w.vm.$nextTick();
    expect(w.find('[data-pending="refund"]').exists()).toBe(false);
    const money = w.get("[data-order-money]");
    expect(money.attributes("data-order-money-state")).toBe("refunded");
    expect(money.text()).toContain("Dinheiro do pedido cancelado: Estornado");
    expect(money.text()).toContain("O cliente lê na loja: “Devolvemos os R$ 18,70 do seu Pix para a mesma conta.”");
    w.unmount();
  });
});

// P1-20: quem só expede abre um pedido pelo sino. O servidor recusa o detalhe (403 de
// permissão), e a tela dizia "Pedido não encontrado ou falha ao carregar".
// WP-G08: a promessa em risco no detalhe. O cartão, a Fila e a lista de Encomendas
// chegam com `#promise` (avisar o cliente) ou `#cancel` (cancelar); as três saídas
// moram na linha da promessa, na faixa "O que falta neste pedido".
describe("detalhe do pedido — promessa em risco", () => {
  const promiseLine = (over: Record<string, unknown> = {}) => ({
    key: "promise", tone: "error", label: "Promessa em risco",
    reason: "4x Baguete de tradição sem reserva. O lote de amanhã foi cancelado.",
    actions: [
      { ref: "contact-customer", label: "Avisar o cliente", enabled: true, reason: "", href: "https://wa.me/5543999990000" },
      { ref: "reschedule-at-pos", label: "Remarcar no PDV", enabled: true, reason: "", href: "https://pdv.example.test/preorders/WEB-1" },
      { ref: "cancel", label: "Cancelar pedido", enabled: true, reason: "", href: "/api/v1/backstage/orders/WEB-1/cancel/" },
    ],
    ...over,
  });
  const emRisco = (over: Partial<OperatorOrderProjection> = {}) =>
    order({ status: "accepted", can_confirm: false, can_cancel: true, pending: [promiseLine()] as never, ...over });
  beforeEach(() => {
    reveal.mockClear();
    routeHash.value = "";
  });

  it("a linha diz o item e o porquê, com as três saídas de nome fixo", () => {
    const w = abrir(emRisco());
    const row = w.get('[data-pending="promise"]');
    expect(row.text()).toContain("Promessa em risco");
    expect(row.text()).toContain("4x Baguete de tradição sem reserva. O lote de amanhã foi cancelado.");
    expect(row.findAll("[data-pending-action]").map((button) => button.text())).toEqual([
      "Avisar o cliente", "Remarcar no PDV", "Cancelar pedido",
    ]);
    expect(row.get('[data-pending-action="contact-customer"]').attributes("href")).toBe("https://wa.me/5543999990000");
    expect(row.get('[data-pending-action="reschedule-at-pos"]').attributes("href")).toBe("https://pdv.example.test/preorders/WEB-1");
    w.unmount();
  });

  it("\"Cancelar pedido\" da linha abre o MESMO diálogo do menu, sem motivo marcado", async () => {
    const w = abrir(emRisco());
    await w.get('[data-pending-action="cancel"]').trigger("click");
    await flushPromises();
    const dialog = w.get("order-reason-dialog-stub");
    expect(dialog.attributes("open")).toBe("true");
    expect(dialog.attributes("initial-key") ?? "").toBe("");
    w.unmount();
  });

  it("chega com #promise: a página vai à linha da promessa", async () => {
    routeHash.value = "#promise";
    const w = abrir(emRisco());
    await flushPromises();
    expect(reveal).toHaveBeenCalledWith("pending:promise");
    expect(w.get('[data-pending="promise"]').attributes("data-focus-target")).toBe("pending:promise");
    expect(w.get("order-reason-dialog-stub").attributes("open")).not.toBe("true");
    w.unmount();
  });

  it("#promise num pedido que já não está em risco não rola a página", async () => {
    routeHash.value = "#promise";
    const w = abrir(order({ status: "accepted", can_confirm: false, pending: [] as never }));
    await flushPromises();
    expect(reveal).not.toHaveBeenCalled();
    w.unmount();
  });

  it("chega com #cancel: o diálogo de cancelar abre", async () => {
    routeHash.value = "#cancel";
    const w = abrir(emRisco());
    await flushPromises();
    expect(w.get("order-reason-dialog-stub").attributes("open")).toBe("true");
    expect(reveal).not.toHaveBeenCalled();
    w.unmount();
  });

  it("#cancel num pedido que não pode ser cancelado leva à linha, onde o cancelar travado diz o porquê", async () => {
    routeHash.value = "#cancel";
    const w = abrir(emRisco({
      can_cancel: false,
      pending: [promiseLine({
        actions: [
          { ref: "cancel", label: "Cancelar pedido", enabled: false, reason: "Pedido em Pronto não pode ser cancelado.", href: "" },
        ],
      })] as never,
    }));
    await flushPromises();
    expect(w.get("order-reason-dialog-stub").attributes("open")).not.toBe("true");
    expect(reveal).toHaveBeenCalledWith("pending:promise");
    expect(w.get("[data-pending-blocked]").text()).toBe("Pedido em Pronto não pode ser cancelado.");
    w.unmount();
  });
});

describe("detalhe do pedido — a leitura que falhou diz por quê", () => {
  const sessao = (role: string) => vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { id: 1 }, surface_role: role }) }));
  beforeEach(() => {
    readForbidden.value = false;
    readNotFound.value = false;
    readError.value = null;
    sessao("orders");
  });
  const semLeitura = () => {
    detalhe.value = null;
    return mount(OrderDetailPage, { global: { stubs, mocks: { $router: { go: vi.fn() } } } });
  };

  it("quem só expede lê por que não abre, e volta para a Saída", () => {
    sessao("expedition");
    readError.value = { statusCode: 403, data: { detail: "Sem permissão." } };
    readForbidden.value = true;
    const w = semLeitura();
    try {
      const denial = w.get("[data-order-forbidden]");
      expect(denial.text()).toContain("Sua conta não abre o detalhe do pedido");
      expect(denial.text()).toContain("O detalhe é de quem gerencia pedidos.");
      expect(denial.text()).toContain("continua no painel da Saída, onde você marca a saída e a retirada.");
      expect(denial.text()).toContain("Abrir a Saída");
      expect(w.text()).not.toContain("não encontrado");
      expect(w.find("[data-order-error]").exists()).toBe(false);
      // A rede respondeu; quem não abre é a conta. O cabeçalho não diz "Sem conexão"
      // nem oferece o menu de um pedido que a pessoa não pode ler.
      expect(w.text()).not.toContain("Sem conexão");
      expect(w.text()).not.toContain("Atualização falhou");
      expect(w.find('[data-action="menu"]').exists()).toBe(false);
    } finally { w.unmount(); }
  });

  it("outra conta sem a permissão: pede o acesso a um gerente", () => {
    sessao("catalog");
    readError.value = { statusCode: 403 };
    readForbidden.value = true;
    const w = semLeitura();
    try {
      expect(w.get("[data-order-forbidden]").text()).toContain("Peça o acesso a um gerente.");
      expect(w.get("[data-order-forbidden]").text()).toContain("Voltar ao Gestor");
    } finally { w.unmount(); }
  });

  it("pedido que não existe diz o código procurado", () => {
    readError.value = { statusCode: 404 };
    readNotFound.value = true;
    const w = semLeitura();
    try {
      expect(w.find("[data-order-forbidden]").exists()).toBe(false);
      expect(w.get("[data-order-error]").text()).toContain("Pedido não encontrado");
      expect(w.get("[data-order-error]").text()).toContain("Não existe pedido com o código WEB-1.");
    } finally { w.unmount(); }
  });

  it("falha de rede não é pedido inexistente", () => {
    readError.value = { statusCode: 503 };
    const w = semLeitura();
    try {
      const failure = w.get("[data-order-error]").text();
      expect(failure).toContain("Não foi possível carregar o pedido");
      expect(failure).toContain("A leitura falhou. Confira a conexão e toque em Atualizar, no menu do pedido.");
      expect(failure).not.toContain("não encontrado");
    } finally { w.unmount(); }
  });
});
