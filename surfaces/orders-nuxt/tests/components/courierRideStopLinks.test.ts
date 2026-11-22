// Entregas (#2491): na corrida de várias paradas o link de acompanhamento é de cada
// parada, oferecido na linha do próprio pedido; a corrida não ganha um link "dela".
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
  change_label: "", group_refusal: "", error: "", dispatch_action: null, dispatch_again_action: null, charge_outdated: null,
  tracking_url: `https://rastreio.example/${ref}`, ...over,
});
function ride(over: Partial<DeliveryRideProjection> = {}): DeliveryRideProjection {
  return {
    key: "776753357", number: 2, state: "route", status_label: "Indo para os clientes",
    stops: [stop("NB-A05", { done: true }), stop("NB-C12"), stop("NB-D20", { tracking_url: "" })],
    driver: null, position: null, called_at: "2026-11-16T17:12:00Z", called_by: "ana", pickup_eta_at: "",
    arrived_pickup_at: "", picked_up_at: "", delivery_eta_at: "", tracking_url: "", cost_display: "", bags: 3,
    undeclared: [], lead_ref: "NB-A05", back_action: null, back_lines: [], cancel_action: null, cancel_state: "",
    cancel_message: "", ...over,
  } as DeliveryRideProjection;
}
const mountDetail = (over: Partial<DeliveryRideProjection> = {}) =>
  mount(Detail, {
    props: { ride: ride(over), origin: null, now: Date.parse("2026-11-16T14:20:00-03:00"), busy: false },
    global: { stubs: { Icon: true, NuxtIcon: true, CourierDeliveriesMap: true } },
  });

describe("Entregas: o link de acompanhamento por parada", () => {
  it("só a parada a caminho, com link provado, oferece o próprio link", () => {
    const w = mountDetail();
    try {
      const links = w.findAll("[data-ride-stop-link]");
      expect(links).toHaveLength(1);
      expect(links[0]!.text()).toBe("Copiar link de acompanhamento");
      expect(w.text()).not.toContain("Link de acompanhamento da corrida.");
    } finally { w.unmount(); }
  });

  it("copia o link DAQUELA parada e diz Copiado só nela", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    const original = globalThis.navigator;
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const w = mountDetail();
    try {
      await w.get("[data-ride-stop-link]").trigger("click");
      await new Promise((r) => setTimeout(r, 0));
      expect(writeText).toHaveBeenCalledWith("https://rastreio.example/NB-C12");
      expect(w.get("[data-ride-stop-link]").text()).toBe("Copiado");
    } finally { w.unmount(); vi.stubGlobal("navigator", original); }
  });

  it("com uma parada só, o link continua sendo o da corrida, sem botão na linha", () => {
    const w = mountDetail({ stops: [stop("NB-C12")] as never, tracking_url: "https://rastreio.example/NB-C12" });
    try {
      expect(w.find("[data-ride-stop-link]").exists()).toBe(false);
      expect(w.text()).toContain("Link de acompanhamento da corrida.");
    } finally { w.unmount(); }
  });
});
