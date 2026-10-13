import { describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

import KdsHistoryDialog from "../../app/components/KdsHistoryDialog.vue";
import type { KDSHistoryEntryProjection, KDSHistoryProjection, KDSTicketProjection } from "../../app/types/kds";
import { nuxtUiStubs } from "../support/nuxtUi";

vi.stubGlobal("computed", computed);

function entry(pk: number, over: Partial<KDSHistoryEntryProjection> = {}): KDSHistoryEntryProjection {
  return {
    ticket: { pk, order_ref: `BAL-261013-0${pk}`, customer_name: "", is_preorder: false } as KDSTicketProjection,
    state: "done",
    items_summary: "1x Croque",
    steps: ["recebido 21:40", "Pronto 21:51 Rafael (tela)"],
    undone: [],
    prep_display: "11 min",
    can_reopen: true,
    reopen_block_reason: "",
    ...over,
  };
}

function history(entries: KDSHistoryEntryProjection[], total = entries.length): KDSHistoryProjection {
  return { instance_ref: "lanches", instance_name: "Lanches", entries, total, query: "" };
}

const NuxtInput = defineComponent({
  name: "NuxtInput",
  inheritAttrs: false,
  props: { modelValue: String },
  emits: ["update:modelValue"],
  setup: (props, { emit, attrs }) => () =>
    h("input", {
      ...attrs,
      value: props.modelValue,
      onInput: (e: Event) => emit("update:modelValue", (e.target as HTMLInputElement).value),
    }),
});
const stubs = {
  ...nuxtUiStubs,
  NuxtInput,
  NuxtBadge: { props: ["label"], template: "<span data-badge>{{ label }}</span>" },
  OperatorScreenState: { props: ["title", "state"], template: "<div data-screen-state>{{ state }} {{ title }}</div>" },
  Icon: true,
};

function mountDialog(props: Record<string, unknown>) {
  return mount(KdsHistoryDialog, { props: { open: true, query: "", history: null, ...props }, global: { stubs } });
}

describe("KdsHistoryDialog: o Histórico de hoje da estação", () => {
  it("lista os pedidos e Reabrir só onde a régua deixa", async () => {
    const reason = "Pedido despachado: não volta à cozinha. Para refazer, peça pelo PDV ou pelo Gestor.";
    const w = mountDialog({
      history: history([entry(131), entry(132, { can_reopen: false, reopen_block_reason: reason })]),
    });
    expect(w.text()).toContain("Histórico de hoje");
    expect(w.findAll("[data-kds-history-row]")).toHaveLength(2);
    expect(w.findAll("[data-kds-history-reopen]")).toHaveLength(1);
    expect(w.get("[data-kds-history-row='132'] [data-kds-history-blocked]").text()).toBe(reason);
    await w.get("[data-kds-history-reopen]").trigger("click");
    expect(w.emitted("reopen")).toEqual([[131]]);
  });

  it("tocar na linha abre o pedido (só leitura)", async () => {
    const one = entry(140);
    const w = mountDialog({ history: history([one]) });
    await w.get("[data-kds-history-view]").trigger("click");
    expect(w.emitted("view")).toEqual([[one]]);
  });

  it("mostra o Pronto desfeito e quem desfez", () => {
    const w = mountDialog({
      history: history([entry(150, { undone: ["Pronto 21:51 Rafael (tela) → desfeito 21:58 Ana"] })]),
    });
    expect(w.get("[data-kds-history-undone]").text()).toBe("Pronto 21:51 Rafael (tela) → desfeito 21:58 Ana");
  });

  it("o cancelado leva o selo e não oferece Reabrir", () => {
    const w = mountDialog({
      history: history([entry(160, { state: "cancelled", can_reopen: false, prep_display: "" })]),
    });
    expect(w.get("[data-badge]").text()).toBe("Cancelado");
    expect(w.find("[data-kds-history-reopen]").exists()).toBe(false);
  });

  it("a busca sobe pelo v-model e o rodapé avisa quando há mais que a lista", async () => {
    const w = mountDialog({ history: history([entry(131)], 140) });
    await w.get("[data-kds-history-search]").setValue("0131");
    expect(w.emitted("update:query")?.at(-1)).toEqual(["0131"]);
    expect(w.get("[data-kds-history-footnote]").text()).toContain("de 140");
  });

  it("sem nada hoje, diz isso", () => {
    const w = mountDialog({ history: history([]) });
    expect(w.get("[data-screen-state]").text()).toContain("Nenhum pedido concluído ou cancelado hoje");
  });
});
