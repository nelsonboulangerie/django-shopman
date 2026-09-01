import { describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import type { OperatorOrderProjection } from "../../app/types/orders";

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
    ...over,
  } as OperatorOrderProjection;
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
