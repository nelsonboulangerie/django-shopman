import { describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import KdsTicketModal from "../../app/components/KdsTicketModal.vue";
import type { KDSTicketProjection } from "../../app/types/kds";
import { nuxtUiStubs } from "../support/nuxtUi";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);

function ticket(over: Partial<KDSTicketProjection> = {}): KDSTicketProjection {
  return {
    pk: 1,
    order_ref: "WEB-20261004-0007",
    channel_icon: "language",
    customer_name: "Ana",
    fulfillment_icon: "storefront",
    created_at_display: "08:00",
    elapsed_seconds: 90,
    target_seconds: 600,
    timer_class: "timer-ok",
    items: [
      { sku: "A", name: "Pão na Chapa", qty: 2, notes: "", stock_warning: "" },
      { sku: "B", name: "Café", qty: 1, notes: "", stock_warning: "" },
    ],
    status: "in_progress",
    previous_tab_ref: "",
    status_label: "Em preparo",
    is_cancelled: false,
    cancelled_at_display: "",
    completed_at_display: "",
    kitchen_note: "",
    customer_note: "",
    test_order_label: "",
    finish_block_label: "",
    finish_block_reason: "",
    volumes: 0,
    volumes_order_ref: "WEB-20261004-0007",
    volumes_revision: "rev",
    started_by: "",
    started_at_display: "",
    ...over,
  };
}

// O diálogo do Nuxt UI vira uma caixa simples: o que se testa é o conteúdo.
const stubs = { Icon: true, ...nuxtUiStubs };

function mountModal(props: Record<string, unknown>) {
  return mount(KdsTicketModal, { props: { open: true, ...props }, global: { stubs } });
}

describe("KdsTicketModal: quem embalou declara os volumes na estação", () => {
  it("abre o − N + com a contagem de itens e Gravar emite o número", async () => {
    const w = mountModal({ ticket: ticket() });
    await w.get("[data-kds-volumes-open]").trigger("click");
    expect(w.get("[data-kds-volumes-draft]").text()).toBe("2");
    await w.get("[aria-label='Um volume a mais']").trigger("click");
    await w.get("[data-kds-volumes-save]").trigger("click");
    expect(w.emitted("volumes")?.[0]).toEqual([3]);
  });

  it("já declarado, o botão diz quantos e parte do número gravado; zero apaga", async () => {
    const w = mountModal({ ticket: ticket({ volumes: 1 }) });
    expect(w.get("[data-kds-volumes-open]").text()).toContain("Volumes: 1 (mudar)");
    await w.get("[data-kds-volumes-open]").trigger("click");
    await w.get("[aria-label='Um volume a menos']").trigger("click");
    expect(w.text()).toContain("Zero apaga");
    await w.get("[data-kds-volumes-save]").trigger("click");
    expect(w.emitted("volumes")?.[0]).toEqual([0]);
  });

  it("ticket de comanda (sem pedido) não oferece o gesto", () => {
    expect(mountModal({ ticket: ticket({ volumes_order_ref: "" }) }).find("[data-kds-volumes]").exists()).toBe(false);
  });
});

describe("KdsTicketModal: quem iniciou", () => {
  it("diz quem iniciou o ticket e a que horas", () => {
    const w = mountModal({ ticket: ticket({ started_by: "joyce", started_at_display: "14:05" }) });
    expect(w.get("[data-kds-started]").text()).toBe("Iniciado por joyce às 14:05");
  });

  it("antes do início, nada", () => {
    expect(mountModal({ ticket: ticket() }).find("[data-kds-started]").exists()).toBe(false);
  });
});

describe("KdsTicketModal: aberto pelo Histórico de hoje, só leitura", () => {
  const history = (over: Record<string, unknown> = {}) => ({
    ticket: ticket({ status: "done" }),
    state: "done",
    items_summary: "2x Pão na Chapa, 1x Café",
    steps: ["recebido 21:40", "iniciado 21:42 Rafael", "Pronto 21:51 Rafael (tela)"],
    undone: ["Pronto 21:45 Rafael (tela) → desfeito 21:47 Ana"],
    prep_display: "9 min",
    can_reopen: true,
    reopen_block_reason: "",
    ...over,
  });

  it("troca o relógio pela trilha e pelo tempo de preparo", () => {
    const w = mountModal({ ticket: ticket({ status: "done", started_by: "Rafael" }), history: history() });
    expect(w.get("[data-kds-ticket-history-prep]").text()).toContain("9 min");
    const trail = w.get("[data-kds-ticket-history-trail]").text();
    expect(trail).toContain("recebido 21:40 · iniciado 21:42 Rafael · Pronto 21:51 Rafael (tela)");
    expect(trail).toContain("desfeito 21:47 Ana");
    expect(w.find("[data-kds-started]").exists()).toBe(false);
  });

  it("volumes só enquanto o pedido está na casa", () => {
    expect(mountModal({ ticket: ticket(), history: history() }).find("[data-kds-volumes]").exists()).toBe(true);
    const gone = history({ can_reopen: false, reopen_block_reason: "Pedido despachado: não volta à cozinha." });
    const w = mountModal({ ticket: ticket(), history: gone });
    expect(w.find("[data-kds-volumes]").exists()).toBe(false);
    expect(w.get("[data-kds-ticket-history-trail]").text()).toContain("Pedido despachado");
  });
});
