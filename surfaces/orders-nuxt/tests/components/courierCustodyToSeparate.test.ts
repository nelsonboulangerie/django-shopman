// #2500: a TaOn retomou a corrida que constava como encerrada, e o troco e a
// maquininha tinham voltado para a casa. O aviso diz o que voltou e leva o
// "Separar de novo", que abre o troco (com o valor da chamada) e a maquininha
// livre; nada é registrado antes do "Separar".
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { fixtureActions } from "../support/orderActions";
import type { CourierBlock } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-11-16T14:20:00-03:00")));
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");

const custodyAction = { ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-custody", label: "Separar de novo", enabled: true };
const courier = {
  status: "D", ride_state: "searching", service_name: "TaOn", status_label: "Procurando entregador", active: true, can_quote: false,
  can_dispatch: false, can_cancel: true, attempts_count: 0,
} as unknown as CourierBlock;
const machines = [
  { ref: "card_machine:3", label: "Azul", enabled: true, reason: "", order_ref: "" },
  { ref: "card_machine:4", label: "Preta", enabled: false, reason: "Saiu com o A12", order_ref: "A12" },
];
const mountPanel = (missing: CourierBlock["custody_to_separate"]) => mount(Panel, {
  props: { courier: { ...courier, custody_to_separate: missing }, busy: false, custodyAction, equipmentOptions: machines },
  global: { stubs: { Icon: true } },
});

describe("Separar de novo (corrida retomada)", () => {
  it("sem nada a separar, não há aviso", () => {
    const w = mountPanel(null);
    try {
      expect(w.find("[data-courier-custody-missing]").exists()).toBe(false);
    } finally { w.unmount(); }
  });

  it("o aviso diz o que voltou para a casa", () => {
    const both = mountPanel({ change_out_suggested_q: 2600, needs_machine: true });
    const change = mountPanel({ change_out_suggested_q: 2600, needs_machine: false });
    const machine = mountPanel({ change_out_suggested_q: 0, needs_machine: true });
    try {
      expect(both.get("[data-courier-custody-missing]").text()).toContain("O troco e a maquininha voltaram para a casa");
      expect(change.get("[data-courier-custody-missing]").text()).toContain("O troco voltou para a casa");
      expect(machine.get("[data-courier-custody-missing]").text()).toContain("A maquininha voltou para a casa");
      expect(both.get("[data-courier-custody-missing]").text()).toContain("A TaOn retomou a corrida. Separe de novo antes de entregar a sacola.");
    } finally { both.unmount(); change.unmount(); machine.unmount(); }
  });

  it("o gesto abre o troco e a maquininha livre; Separar manda os dois", async () => {
    const w = mountPanel({ change_out_suggested_q: 2600, needs_machine: true });
    try {
      expect(w.find("[data-courier-separate-form]").exists()).toBe(false);
      await w.get("[data-courier-separate]").trigger("click");
      expect(w.emitted("separate")).toBeUndefined();
      const field = w.get("[data-courier-separate-change]");
      const input = (field.element.tagName === "INPUT" ? field.element : field.get("input").element) as HTMLInputElement;
      expect(input.value).toBe("26,00");
      expect(w.get("[data-courier-separate-go]").text()).toBe("Separar R$ 26,00 e a maquininha Azul");
      await w.get("[data-courier-separate-go]").trigger("click");
      expect(w.emitted("separate")).toEqual([[{ change_out: "26,00", equipment: ["card_machine:3"] }]]);
    } finally { w.unmount(); }
  });

  it("Agora não fecha sem registrar nada", async () => {
    const w = mountPanel({ change_out_suggested_q: 2600, needs_machine: false });
    try {
      await w.get("[data-courier-separate]").trigger("click");
      await w.get("[data-courier-separate-keep]").trigger("click");
      expect(w.find("[data-courier-separate-form]").exists()).toBe(false);
      expect(w.emitted("separate")).toBeUndefined();
    } finally { w.unmount(); }
  });

  it("o rótulo diz o que sai: só o troco, ou só a maquininha", async () => {
    const change = mountPanel({ change_out_suggested_q: 2600, needs_machine: false });
    const machine = mountPanel({ change_out_suggested_q: 0, needs_machine: true });
    try {
      await change.get("[data-courier-separate]").trigger("click");
      await machine.get("[data-courier-separate]").trigger("click");
      expect(change.get("[data-courier-separate-go]").text()).toBe("Separar R$ 26,00");
      expect(machine.get("[data-courier-separate-go]").text()).toBe("Separar a maquininha Azul");
    } finally { change.unmount(); machine.unmount(); }
  });
});
