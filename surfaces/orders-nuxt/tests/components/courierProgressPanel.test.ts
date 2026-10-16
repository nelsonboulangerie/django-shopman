import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { CourierBlock } from "../../app/types/orders";

// O painel Entregador mostra o andamento da TaOn: estado em palavra (selo),
// quando chega para coletar, quando a entrega está prevista, e o aviso de
// quando a TaOn parou de informar (13/10/2026: a corrida ficou parada em D).

const NOW = Date.parse("2026-10-13T15:42:00-03:00");
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useNowTick", () => computed(() => NOW));
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");

const ride = (extra: Partial<CourierBlock>) =>
  ({
    status: "A",
    status_label: "Entregador a caminho da loja",
    active: true,
    can_quote: false,
    can_dispatch: false,
    can_cancel: false,
    attempts_count: 0,
    driver: null,
    tracking_url: "",
    confirmation_code: "",
    estimate_display: "",
    final_value_display: "",
    error: null,
    ...extra,
  }) as CourierBlock;

const mountPanel = (courier: CourierBlock) =>
  mount(Panel, { props: { courier, busy: false }, global: { stubs: { Icon: true } } });

describe("andamento da corrida", () => {
  it("aceita: chega para coletar em ~X min e entrega prevista", () => {
    const wrapper = mountPanel(
      ride({ pickup_eta_at: "2026-10-13T18:49:00+00:00", delivery_eta_at: "2026-10-13T18:58:00+00:00" }),
    );
    const progress = wrapper.get('[data-testid="courier-progress"]').text();
    expect(progress).toContain("Chega para coletar em ~7 min");
    expect(progress).toContain("Entrega prevista ~15:58");
    expect(wrapper.find('[data-testid="courier-stale"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("sem notícias da TaOn: aviso com a hora", () => {
    const wrapper = mountPanel(
      ride({ status: "D", status_label: "Procurando entregador", sync_since: "2026-10-13T18:41:46+00:00" }),
    );
    const stale = wrapper.get('[data-testid="courier-stale"]');
    expect(stale.text()).toContain("A TaOn não informa a corrida desde 15:41.");
    expect(stale.text()).toContain("Confira no painel da TaOn.");
    wrapper.unmount();
  });

  it("o veículo diz modelo, cor e placa", () => {
    const wrapper = mountPanel(
      ride({
        driver: { name: "Carlos", phone: "", vehicle_model: "CG 160", vehicle_color: "Vermelha", vehicle_plate: "ABC1D23" },
      }),
    );
    expect(wrapper.text()).toContain("CG 160 · Vermelha · ABC1D23");
    wrapper.unmount();
  });
});
