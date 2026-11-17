// Detalhe da corrida na seção Entregas (revisão das Entregas, F7a): o estado da
// parada abre com maiúscula, a origem da posição fica fora do mapa (dentro, a loja
// cobria a etiqueta e ela virava "Posição pe…") e, sem coordenada da loja, o mapa
// não põe a loja na casa do primeiro cliente.
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { DeliveryRideProjection } from "../../app/generated/ordersContract";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-11-16T14:20:00-03:00")));
const { default: Detail } = await import("../../app/components/CourierRideDetail.vue");

const stop = (ref: string, over: Record<string, unknown> = {}) => ({
  ref, code: ref.slice(-3), customer: "Ana", place: "Centro", address: "Rua das Flores, 123", latitude: -21.17,
  longitude: -47.81, stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false,
  change_label: "", group_refusal: "", error: "", dispatch_action: null, ...over,
});
function ride(over: Partial<DeliveryRideProjection> = {}): DeliveryRideProjection {
  return {
    key: "776753357", number: 2, state: "route", status_label: "Indo para os clientes",
    stops: [stop("NB-261116-A05", { done: true }), stop("NB-261116-C12"), stop("NB-261116-D20", { volumes: 0 })],
    driver: null, position: { latitude: -21.16, longitude: -47.8 },
    called_at: "2026-11-16T17:12:00Z", called_by: "ana", pickup_eta_at: "", arrived_pickup_at: "", picked_up_at: "",
    delivery_eta_at: "", tracking_url: "", cost_display: "", bags: 3, undeclared: [], lead_ref: "NB-261116-A05",
    back_action: null, back_lines: [], cancel_action: null, cancel_state: "", cancel_message: "",
    ...over,
  } as DeliveryRideProjection;
}
const MapStub = { name: "CourierDeliveriesMap", props: ["origin"], template: "<div data-map-stub />" };
const mountDetail = (over: Partial<DeliveryRideProjection> = {}, origin: unknown = null) =>
  mount(Detail, {
    props: { ride: ride(over), origin, now: Date.parse("2026-11-16T14:20:00-03:00"), busy: false },
    global: { stubs: { Icon: true, NuxtIcon: true, CourierDeliveriesMap: MapStub } },
  });

describe("Entregas: o detalhe da corrida e o mapa", () => {
  it("o estado de cada parada abre com maiúscula", () => {
    const w = mountDetail();
    try {
      const text = w.text();
      expect(text).toContain("Entregue");
      expect(text).toContain("Indo para cá");
      expect(text).toContain("Sacolas?");
      expect(text).not.toMatch(/\bentregue\b|\bindo para cá\b|\bsacolas\?/);
    } finally { w.unmount(); }
  });

  it("a origem da posição vem por extenso, fora do mapa", () => {
    const w = mountDetail();
    try {
      const label = w.get("[data-ride-position-source]");
      expect(label.text()).toBe("Posição do entregador pela TaOn");
      expect(w.get("[data-map-stub]").element.contains(label.element)).toBe(false);
    } finally { w.unmount(); }
  });

  it("sem posição, a etiqueta não aparece", () => {
    const w = mountDetail({ position: null });
    try {
      expect(w.find("[data-ride-position-source]").exists()).toBe(false);
    } finally { w.unmount(); }
  });

  it("sem coordenada da loja, o mapa aparece com as paradas e a loja não vira o primeiro cliente", () => {
    const w = mountDetail();
    try {
      const map = w.findComponent(MapStub);
      expect(w.find("[data-map-stub]").exists()).toBe(true);
      expect(map.props("origin")).toBeNull();
    } finally { w.unmount(); }
  });
});
