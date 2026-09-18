import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import KdsTicketCard from "../../app/components/KdsTicketCard.vue";
import type { KDSTicketProjection } from "../../app/types/kds";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui). Reatividade
// Vue REAL.
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("nextTick", nextTick);
vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);

function ticket(over: Partial<KDSTicketProjection> = {}): KDSTicketProjection {
  return {
    pk: 1,
    order_ref: "WEB-20260625-0007",
    channel_icon: "language",
    customer_name: "Ana",
    fulfillment_icon: "storefront",
    created_at_display: "08:00",
    elapsed_seconds: 90,
    target_seconds: 600,
    timer_class: "timer-ok",
    items: [
      {
        sku: "A",
        name: "Pão na Chapa",
        qty: 2,
        notes: "",
        stock_warning: "",
      },
      {
        sku: "B",
        name: "Café",
        qty: 1,
        notes: "sem açúcar",
        stock_warning: "",
      },
    ],
    status: "in_progress",
    previous_tab_ref: "",
    is_scheduled: false,
    is_expedition: false,
    status_label: "",
    is_cancelled: false,
    cancelled_at_display: "",
    completed_at_display: "",
    kitchen_note: "",
    customer_note: "",
    ...over,
  };
}

const stubs = { Icon: true };
const mountCard = (props: Record<string, unknown>) =>
  mount(KdsTicketCard, { props, global: { stubs } });

describe("KdsTicketCard — render", () => {
  it("mostra o código (final da ref), a minutagem e os itens", () => {
    const t = mountCard({ ticket: ticket() }).text();
    expect(t).toContain("0007"); // hero code = final da ref
    expect(t).toContain("Pão na Chapa");
    expect(t).toContain("2×");
    expect(t).toContain("1×");
    expect(t).toContain("1m"); // 90s → "1m" (elapsedLabel)
  });

  it("mantém a antiga comanda riscada depois que o pedido ganha nova referência", () => {
    const wrapper = mountCard({ ticket: ticket({ order_ref: "A42", previous_tab_ref: "Mesa 5" }) });
    expect(wrapper.text()).toContain("A42");
    expect(wrapper.text()).toContain("Comanda Mesa 5");
    expect(wrapper.find(".line-through").exists()).toBe(true);
  });

  it("renderiza a nota do item (observação da cozinha)", () => {
    expect(mountCard({ ticket: ticket() }).text()).toContain("sem açúcar");
  });

  it("mostra a nota da cozinha (operador) e a nota do cliente quando presentes", () => {
    const t = mountCard({
      ticket: ticket({ kitchen_note: "Bem assado. Sem cebola.", customer_note: "Cortar ao meio" }),
    }).text();
    expect(t).toContain("Bem assado. Sem cebola.");
    expect(t).toContain("Cortar ao meio");
  });

  it("sem notas de pedido → não renderiza o banner de notas", () => {
    // Sem kitchen_note/customer_note o bloco de notas do pedido não aparece
    // (apenas a observação por-item, se houver).
    const t = mountCard({
      ticket: ticket({ items: [{ sku: "A", name: "Pão", qty: 1, notes: "", stock_warning: "" }] }),
    }).text();
    expect(t).not.toContain("Bem assado");
  });

  it("mostra o aviso de estoque quando presente", () => {
    const w = mountCard({
      ticket: ticket({
        items: [
          {
            sku: "A",
            name: "Pão",
            qty: 1,
            notes: "",
            stock_warning: "Massa acabando",
          },
        ],
      }),
    });
    expect(w.text()).toContain("Massa acabando");
  });

  it("mostra encomenda futura como prévia, sem alvo de toque", () => {
    const wrapper = mountCard({ ticket: ticket({ is_scheduled: true, status: "scheduled" }) });
    expect(wrapper.text()).toContain("Agendado");
    expect(wrapper.text()).toContain("Prévia · libera na data");
    expect(wrapper.find("[data-kds-tap]").exists()).toBe(false);
  });

  it("nunca trunca nome de item nem observação: quebram linha", () => {
    const longo = "Croissant de amêndoas recheado com creme de pistache e framboesa";
    const w = mountCard({
      ticket: ticket({
        items: [{ sku: "A", name: longo, qty: 1, notes: "sem açúcar de confeiteiro, embalar separado", stock_warning: "" }],
      }),
    });
    expect(w.text()).toContain(longo);
    expect(w.find("ul").html()).not.toContain("truncate");
    expect(w.find("ul").html()).not.toContain("line-clamp");
  });

  it("marca ticket adicional e pedido de entrega no cabeçalho", () => {
    const t = mountCard({
      ticket: ticket({ fulfillment_icon: "local_shipping" }),
      addition: true,
    }).text();
    expect(t).toContain("Adicional");
    expect(t).toContain("Entrega");
  });

  it("escala de densidade mapeia aos papéis do canon: compact=title text-xl, roomy=display text-4xl", () => {
    expect(
      mountCard({ ticket: ticket(), density: "compact" })
        .find("article p")
        .classes(),
    ).toContain("text-xl");
    expect(
      mountCard({ ticket: ticket(), density: "roomy" })
        .find("article p")
        .classes(),
    ).toContain("text-4xl");
  });
});

describe("KdsTicketCard — o toque no cabeçalho", () => {
  afterEach(() => vi.useRealTimers());

  it("pendente: um toque emite start e a faixa convida a iniciar", async () => {
    const w = mountCard({ ticket: ticket({ status: "pending" }) });
    expect(w.get("[data-kds-strip]").text()).toContain("Toque para iniciar");
    await w.get("[data-kds-tap]").trigger("click");
    expect(w.emitted("start")).toHaveLength(1);
    expect(w.emitted("finish")).toBeUndefined();
  });

  it("em preparo (já armado): um toque emite finish", async () => {
    const w = mountCard({ ticket: ticket({ status: "in_progress" }) });
    expect(w.get("[data-kds-strip]").text()).toContain("toque para finalizar");
    await w.get("[data-kds-tap]").trigger("click");
    expect(w.emitted("finish")).toHaveLength(1);
  });

  it("toque duplo não inicia e finaliza: o finalizar só arma depois do intervalo", async () => {
    vi.useFakeTimers();
    const w = mountCard({ ticket: ticket({ status: "pending" }) });
    await w.get("[data-kds-tap]").trigger("click");
    await w.setProps({ ticket: ticket({ status: "in_progress" }) }); // otimista
    await w.get("[data-kds-tap]").trigger("click"); // o quique do dedo
    expect(w.emitted("finish")).toBeUndefined();
    vi.advanceTimersByTime(1000);
    await nextTick();
    await w.get("[data-kds-tap]").trigger("click");
    expect(w.emitted("finish")).toHaveLength(1);
  });

  it("item cancelado sem Ciente: o toque emite blocked, nunca finish", async () => {
    const w = mountCard({ ticket: ticket({ status: "in_progress" }), blocked: true });
    expect(w.get("[data-kds-strip]").text()).toContain("Item cancelado");
    await w.get("[data-kds-tap]").trigger("click");
    expect(w.emitted("blocked")).toHaveLength(1);
    expect(w.emitted("finish")).toBeUndefined();
  });

  it("o `i` abre o detalhe sem acionar o gesto do cabeçalho", async () => {
    const w = mountCard({ ticket: ticket({ status: "pending" }) });
    await w.get("[data-kds-open]").trigger("click");
    expect(w.emitted("open")).toHaveLength(1);
    expect(w.emitted("start")).toBeUndefined();
  });
});
