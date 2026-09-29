import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import KdsExitPreparingCard from "../../app/components/KdsExitPreparingCard.vue";
import type { KDSExitPreparingCardProjection, KDSExitStationChipProjection } from "../../app/types/kds";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);

function chip(over: Partial<KDSExitStationChipProjection> = {}): KDSExitStationChipProjection {
  return {
    station_ref: "lanches",
    station_name: "Lanches",
    prints: true,
    state: "pending",
    state_label: "na fila",
    paper_label: "impresso às 10:42",
    paper_failed: false,
    cancelled_items: 0,
    can_mark_ready: true,
    ...over,
  };
}

function card(stations: KDSExitStationChipProjection[]): KDSExitPreparingCardProjection {
  return {
    pk: 42,
    order_ref: "WEB-20260926-1234",
    channel_icon: "language",
    customer_name: "Ana",
    fulfillment_icon: "storefront",
    fulfillment_label: "Retirada",
    is_delivery: false,
    fired_at_display: "10:40",
    elapsed_seconds: 180,
    stations,
    is_scheduled: false,
    test_order_label: "",
  };
}

const mountCard = (props: Record<string, unknown>) =>
  mount(KdsExitPreparingCard, { props, global: { stubs: { Icon: true } } });

describe("KdsExitPreparingCard — um chip por estação", () => {
  it("a estação sem tela diz quando o papel saiu e oferece Pronto", async () => {
    const w = mountCard({ card: card([chip()]) });
    const row = w.get("[data-testid=exit-station-chip]");
    expect(row.text()).toContain("Lanches");
    expect(row.text()).toContain("impresso às 10:42");
    const button = row.get("button");
    expect(button.text()).toContain("Pronto");
    expect(button.attributes("aria-label")).toBe("Lanches pronto no pedido 1234");
    await button.trigger("click");
    expect(w.emitted("ready")).toEqual([["lanches"]]);
  });

  it("a estação de tela só mostra o estado — ela dá baixa sozinha", () => {
    const w = mountCard({
      card: card([
        chip({ station_ref: "cafes", station_name: "Cafés", prints: false, state: "in_progress", state_label: "em preparo", paper_label: "", can_mark_ready: false }),
      ]),
    });
    const row = w.get("[data-testid=exit-station-chip]");
    expect(row.text()).toContain("Cafés");
    expect(row.text()).toContain("em preparo");
    expect(row.find("button").exists()).toBe(false);
  });

  it("estação pronta fica no card, sem botão", () => {
    const w = mountCard({
      card: card([chip({ state: "done", state_label: "pronto", can_mark_ready: false })]),
    });
    const row = w.get("[data-testid=exit-station-chip]");
    expect(row.text()).toContain("pronto");
    expect(row.find("button").exists()).toBe(false);
  });

  it("papel que não saiu grita e manda avisar a estação", () => {
    const w = mountCard({
      card: card([chip({ paper_label: "não imprimiu", paper_failed: true })]),
    });
    expect(w.get("[data-testid=exit-station-chip]").text()).toContain("não imprimiu — avise a estação");
  });

  it("o Pronto em voo fica desabilitado (sem toque duplo)", () => {
    const w = mountCard({ card: card([chip()]), busyStations: new Set(["lanches"]) });
    expect(w.get("[data-testid=exit-station-chip] button").attributes("disabled")).toBeDefined();
  });

  it("item retirado depois do disparo aparece por extenso", () => {
    const w = mountCard({ card: card([chip({ cancelled_items: 2 })]) });
    expect(w.get("[data-testid=exit-station-chip]").text()).toContain("2 itens cancelados");
  });
});
