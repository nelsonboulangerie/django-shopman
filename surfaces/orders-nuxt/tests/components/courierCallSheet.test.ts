// O sheet de chamar (#2876): o MESMO nas Entregas, no cartão Pronto do Painel e no
// detalhe do pedido. Aqui o que a confirmação em linha do Painel cobrava passou a
// morar: a custódia (troco e maquininha), o companheiro marcado como "Sugestão da
// casa" (decisão 1 = A), a cotação SÓ leitura e o "Chamar só A47".
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { CallSheetCompanions, CallSheetRide } from "../../app/components/CourierCallSheet.vue";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
const { default: Sheet } = await import("../../app/components/CourierCallSheet.vue");

const ride = (extra: Partial<CallSheetRide> = {}): CallSheetRide => ({
  number: 3, letter: "C", color: { bg: "#e9b949", fg: "#1c1917" },
  stops: [
    { ref: "A47", code: "A47", customer: "Ana", place: "Gleba Palhano", change_out_suggested_q: 5000, change: "50,00" },
    { ref: "C03", code: "C03", customer: "Caio", place: "Gleba Palhano", change_out_suggested_q: 2000, change: "20,00" },
  ],
  lines: [], late: "", needsMachine: false, machine: "", carriers: [], carrier: "", notice: "", others: [],
  otherValue: "", noteLabel: "", note: "", ...extra,
});
const companions = (): CallSheetCompanions => ({
  choices: [{ ref: "C03", code: "C03", customer: "Caio", place: "Gleba Palhano", stage: "Pronto", note: "Troco para R$ 50,00",
    suggested: true, checked: true, disabled: false }],
  lines: [
    { text: "Juntas: R$ 11,00 · 18 min · 7,4 km ✔", strong: true },
    { text: "Separadas sairiam R$ 17,00", strong: false },
  ],
  late: "C03 chega uns 6 min depois.",
  note: null,
});
const mountSheet = (props: Record<string, unknown> = {}) =>
  mount(Sheet, {
    props: {
      open: true, title: "Chamar entregador para A47", lines: [], rides: [ride()], machineItems: [],
      callLabel: "Chamar corrida com A47 e C03", canCall: true, reason: "", busy: false, ...props,
    },
    global: { stubs: { NuxtIcon: true, RideCarrierChips: true, CourierDeliveriesMap: true } },
  });

describe("o sheet aberto por um pedido", () => {
  it("o companheiro da sugestão vem marcado, com o selo, e a cotação é só leitura", async () => {
    const w = mountSheet({ companions: companions(), aloneLabel: "Chamar só A47" });
    try {
      const block = w.get("[data-call-sheet-companions]");
      expect(block.text()).toContain("Vai junto nesta corrida?");
      expect(block.get('[role="checkbox"]').attributes("aria-checked")).toBe("true");
      expect(block.get("[data-call-sheet-suggested]").text()).toContain("Sugestão da casa");
      // O ✔ não é botão: as duas linhas são texto, a mais barata em destaque.
      const lines = block.get("[data-call-sheet-suggestion]").findAll("p");
      expect(lines.map((line) => line.text())).toEqual([
        "Juntas: R$ 11,00 · 18 min · 7,4 km ✔", "Separadas sairiam R$ 17,00", "C03 chega uns 6 min depois.",
      ]);
      expect(lines[0]!.classes()).toContain("text-highlighted");
      expect(lines[1]!.classes()).toContain("text-muted");
      expect(block.findAll("button").filter((b) => b.text().includes("✔"))).toHaveLength(0);
      // Desmarcar devolve o gesto; quem decide é a página.
      await block.get('[role="checkbox"]').trigger("click");
      expect(w.emitted("toggle")).toEqual([["C03"]]);
    } finally { w.unmount(); }
  });

  it("Chamar só A47 é um toque ao lado do principal; o principal diz a corrida inteira", async () => {
    const w = mountSheet({ companions: companions(), aloneLabel: "Chamar só A47" });
    try {
      expect(w.get("[data-call-sheet-confirm]").text()).toBe("Chamar corrida com A47 e C03");
      await w.get("[data-call-sheet-alone]").trigger("click");
      expect(w.emitted("alone")).toHaveLength(1);
      expect(w.emitted("confirm")).toBeUndefined();
      await w.get("[data-call-sheet-confirm]").trigger("click");
      expect(w.emitted("confirm")).toHaveLength(1);
    } finally { w.unmount(); }
  });
});

describe("o que o entregador leva", () => {
  it("o troco de cada pedido vem preenchido e se corrige ali; a gaveta soma", async () => {
    const w = mountSheet({ drawer: "Sai da gaveta: R$ 70,00 de troco." });
    try {
      const custody = w.get("[data-call-sheet-custody]");
      expect(custody.text()).toContain("O entregador leva");
      expect(custody.text()).toContain("Troco do pedido A47");
      const input = w.get('input[aria-label="Troco para A47"]');
      expect((input.element as HTMLInputElement).value).toBe("50,00");
      await input.setValue("60,00");
      expect(w.emitted("change")?.at(-1)).toEqual(["A47", "60,00"]);
      expect(w.get("[data-call-sheet-drawer]").text()).toBe("Sai da gaveta: R$ 70,00 de troco.");
    } finally { w.unmount(); }
  });

  it("uma maquininha livre: a frase diz qual", () => {
    const w = mountSheet({
      rides: [ride({ needsMachine: true, machine: "machine:azul" })],
      machineItems: [{ label: "Azul", value: "machine:azul" }],
    });
    try {
      expect(w.get("[data-call-sheet-machine]").text()).toContain("Azul, a única livre");
    } finally { w.unmount(); }
  });

  it("nenhuma maquininha livre: diz, e o chamar espera com o motivo", async () => {
    const w = mountSheet({
      rides: [ride({ needsMachine: true, machine: "" })],
      canCall: false,
      reason: "Faltam maquininhas: 1 corridas levam cartão e nenhuma está livre.",
    });
    try {
      expect(w.get("[data-call-sheet-machine]").text()).toContain("Nenhuma livre");
      expect(w.get("[data-call-sheet-reason]").text()).toContain("nenhuma está livre");
      const confirm = w.get("[data-call-sheet-confirm]");
      expect(confirm.attributes("disabled")).toBeDefined();
      await confirm.trigger("click");
      expect(w.emitted("confirm")).toBeUndefined();
    } finally { w.unmount(); }
  });

  it("pedido pago: nada a levar, o bloco nem aparece", () => {
    const paid = ride({ stops: ride().stops.map((stop) => ({ ...stop, change_out_suggested_q: 0, change: "" })) });
    const w = mountSheet({ rides: [paid] });
    try {
      expect(w.find("[data-call-sheet-custody]").exists()).toBe(false);
      expect(w.find("[data-call-sheet-drawer]").exists()).toBe(false);
    } finally { w.unmount(); }
  });
});

describe("o sheet das sugestões (página Entregas)", () => {
  it("sem pedido de origem, sem 'Vai junto' e sem 'Chamar só'; a linha de baixo conta os pedidos", () => {
    const w = mountSheet({ title: "Chamar a corrida C", callLabel: "Chamar a corrida C" });
    try {
      expect(w.find("[data-call-sheet-companions]").exists()).toBe(false);
      expect(w.find("[data-call-sheet-alone]").exists()).toBe(false);
      expect(w.text()).toContain("2 pedidos. A corrida é paga pela casa e o frete dos clientes não muda.");
    } finally { w.unmount(); }
  });
});
