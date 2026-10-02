// O detalhe do pedido, a MESMA tela no Gestor e no PDV (decisão do dono, 28/09/2026).
// O componente desenha as seções comuns; o que muda entre as telas entra pelos
// slots, e o que cada contexto pode fazer vem do servidor (ação `comment`).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { h, type VNode } from "vue";

import OperatorOrderDetail from "../../app/components/OperatorOrderDetail.vue";
import type { OperatorOrderDetail as Detail } from "../../app/types/orderDetail";

const COMMENT = { ref: "comment", label: "Comentar", enabled: true, reason: "", payload_schema: {} };

function order(overrides: Partial<Detail> = {}): Detail {
  return {
    ref: "ORD-1",
    status: "ready",
    status_label: "Pronto",
    context: "orders",
    actions: [COMMENT],
    channel_ref: "web",
    channel_icon: "language",
    total_display: "R$ 42,00",
    customer_name: "Ana",
    customer_ref: "CLI-1",
    customer_phone: "(43) 99999-0000",
    customer_phone_uri: "tel:+5543999990000",
    customer_whatsapp_url: "https://wa.me/5543999990000",
    customer_email: "",
    customer_relay_phone: "",
    customer_relay_code: "",
    customer_relay_expires_at: "",
    fulfillment_type: "pickup",
    fulfillment_label: "Retirada",
    schedule_label: "Sáb, 27/09 · 08h às 10h",
    delivery_address: "",
    delivery_instructions: "",
    payment_method_label: "Pix",
    payment_status_label: "Pago",
    payment_link_notice: "",
    test_order_notice: "",
    is_gift: false,
    gift_recipient_name: "",
    gift_recipient_phone: "",
    gift_message: "",
    gift_hide_values: false,
    customer_profile: null,
    fiscal_status_label: "",
    fiscal_links: [],
    items: [{ sku: "PAO", name: "Pão francês", qty: "2", unit_price_display: "R$ 1,00", total_display: "R$ 2,00" }],
    customer_note: "",
    kitchen_note: "",
    timeline: [],
    ...overrides,
  };
}

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
async function mount(props: Record<string, unknown>, slots: Record<string, () => VNode> = {}) {
  mounted = await mountSuspended(OperatorOrderDetail, {
    props,
    slots,
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

afterEach(() => {
  mounted?.unmount();
  mounted = null;
});

describe("OperatorOrderDetail", () => {
  it("desenha o resumo e diz qual contexto está lendo", async () => {
    const wrapper = await mount({ order: order({ context: "pos" }) });

    expect(wrapper.get("[data-order-detail]").attributes("data-order-context")).toBe("pos");
    expect(wrapper.get("[data-order-status]").text()).toBe("Pronto");
    expect(wrapper.get("[data-order-total]").text()).toBe("R$ 42,00");
    expect(wrapper.get("[data-order-schedule]").text()).toContain("Sáb, 27/09");
    expect(wrapper.get("[data-order-items]").text()).toContain("Pão francês");
  });

  it("a etiqueta de status do pedido sai quando a tela já diz a situação com a dela (P5, só o PDV)", async () => {
    // Padrão igual ao de sempre: o Gestor não passa a opção e continua com a etiqueta.
    const standard = await mount({ order: order() });
    expect(standard.find("[data-order-status]").exists()).toBe(true);
    standard.unmount();

    const counter = await mount({ order: order({ context: "pos" }), showStatus: false });
    expect(counter.find("[data-order-status]").exists()).toBe(false);
    // O resto do resumo continua: canal e total.
    expect(counter.get("[data-order-summary]").text()).toContain("web");
    expect(counter.get("[data-order-total]").text()).toBe("R$ 42,00");
  });

  it("os slots do contexto entram no lugar certo: saldo no resumo, barra de ações depois dele", async () => {
    const wrapper = await mount(
      { order: order() },
      {
        summary: () => h("p", { "data-slot-summary": "" }, "Falta receber R$ 10,00"),
        actions: () => h("div", { "data-slot-actions": "" }, "Receber e entregar"),
        "after-profile": () => h("div", { "data-slot-after-profile": "" }, "Entregador"),
      },
    );

    expect(wrapper.get("[data-order-summary] [data-slot-summary]").text()).toBe("Falta receber R$ 10,00");
    // A barra fica FORA do resumo, na coluna de seções.
    expect(wrapper.find("[data-order-summary] [data-slot-actions]").exists()).toBe(false);
    expect(wrapper.get("[data-slot-actions]").text()).toBe("Receber e entregar");
    expect(wrapper.get("[data-slot-after-profile]").text()).toBe("Entregador");
  });

  it("perfil do cliente e fiscal só aparecem com o que o servidor mandou", async () => {
    const bare = await mount({ order: order() });
    expect(bare.find("[data-customer-profile]").exists()).toBe(false);
    expect(bare.find("[data-order-fiscal]").exists()).toBe(false);
    bare.unmount();

    const full = await mount({
      order: order({
        customer_profile: {
          orders_label: "12 pedidos",
          last_order_display: "há 3 dias",
          average_ticket_display: "",
          favorite_product: "Croissant",
          segment_label: "Fiel",
          segment_tone: "success",
          notes: "",
          dietary_restrictions: "Sem lactose",
          birthday_display: "",
          is_birthday_today: false,
        },
        fiscal_status_label: "NFC-e autorizada",
        fiscal_links: [{ label: "DANFE", href: "/danfe/ORD-1" }],
      }),
    });
    expect(full.get("[data-customer-history]").text()).toBe("12 pedidos · última compra há 3 dias");
    expect(full.get("[data-customer-habits]").text()).toBe("costuma levar Croissant");
    expect(full.get("[data-customer-segment]").text()).toBe("Fiel");
    expect(full.get("[data-customer-restrictions]").text()).toBe("Sem lactose");
    expect(full.get("[data-order-fiscal]").text()).toContain("NFC-e autorizada");
    expect(full.get("[data-order-fiscal] a").attributes("href")).toBe("/danfe/ORD-1");
  });

  it("pedido do iFood com o código vencido diz que a central não repassa mais", async () => {
    const wrapper = await mount({
      order: order({ customer_whatsapp_url: "", customer_relay_phone: "0800 000 0000", customer_relay_code: "" }),
    });

    expect(wrapper.find("[data-contact-whatsapp]").exists()).toBe(false);
    expect(wrapper.get("[data-contact-relay-expired]").text()).toContain("Código vencido");
    expect(wrapper.get("[data-contact-phone]").text()).toBe("Ligar pela central");
  });

  it("a nota da cozinha é leitura por padrão e editor quando a tela o entrega", async () => {
    const read = await mount({ order: order({ kitchen_note: "Sem gergelim" }) });
    expect(read.get("[data-kitchen-note]").text()).toContain("Sem gergelim");
    read.unmount();

    const edit = await mount(
      { order: order({ kitchen_note: "Sem gergelim" }) },
      { "kitchen-note": () => h("textarea", { "data-slot-kitchen-editor": "" }) },
    );
    expect(edit.find("[data-kitchen-note]").exists()).toBe(false);
    expect(edit.find("[data-slot-kitchen-editor]").exists()).toBe(true);
  });

  it("histórico vazio diz que está vazio; comentário de gente tem marca própria", async () => {
    const empty = await mount({ order: order() });
    expect(empty.get("[data-order-timeline-empty]").text()).toBe("Ainda não há nada no histórico deste pedido.");
    empty.unmount();

    const wrapper = await mount({
      order: order({
        timeline: [
          { label: "Pedido criado", event_type: "created", timestamp_display: "08:00", actor: "", detail: "" },
          { label: "Cliente pediu sem açúcar", event_type: "operator_comment", timestamp_display: "08:05", actor: "Maria", detail: "" },
        ],
      }),
    });
    const rows = wrapper.findAll("[data-order-timeline] li");
    expect(rows).toHaveLength(2);
    expect(rows[1]!.text()).toContain("08:05 · Maria");
    expect(rows[1]!.find("span").classes()).toContain("bg-primary");
  });

  it("comentar só aparece quando o servidor oferece a ação neste contexto", async () => {
    const denied = await mount({
      order: order({ actions: [{ ...COMMENT, enabled: false, reason: "Sem permissão" }] }),
    });
    expect(denied.find("[data-order-comment]").exists()).toBe(false);
    denied.unmount();

    const none = await mount({ order: order({ actions: [] }) });
    expect(none.find("[data-order-comment]").exists()).toBe(false);
  });

  it("envia o comentário sem os espaços das pontas, e nunca vazio ou ocupado", async () => {
    const wrapper = await mount({ order: order(), comment: "  sem cebola  " });
    await wrapper.get("[data-order-comment-submit]").trigger("click");
    expect(wrapper.emitted("comment")).toEqual([["sem cebola"]]);

    await wrapper.setProps({ comment: "   " });
    expect(wrapper.get("[data-order-comment-submit]").attributes("disabled")).toBeDefined();

    await wrapper.setProps({ comment: "outra", busy: true });
    expect(wrapper.get("[data-order-comment-submit]").attributes("disabled")).toBeDefined();
    expect(wrapper.emitted("comment")).toHaveLength(1);
  });

  it("presente sem destinatário vira instrução de embalar", async () => {
    const wrapper = await mount({ order: order({ is_gift: true, gift_hide_values: true }) });
    expect(wrapper.get("[data-gift-block]").text()).toContain("Embalar para presente");
    expect(wrapper.find("[data-gift-hide-values]").exists()).toBe(true);
  });
});
