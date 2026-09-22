import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import IFoodChannelStore from "../../app/components/IFoodChannelStore.vue";
import type { IFoodStoreProjection } from "../../app/types/ifoodStore";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);

const state = ref<IFoodStoreProjection | null>(null);
vi.stubGlobal("useIFoodStore", () => ({ store: state, refresh: vi.fn() }));

function projection(over: Partial<IFoodStoreProjection> = {}): IFoodStoreProjection {
  return {
    enabled: true,
    governs: true,
    channel_off: false,
    can_open_channels: true,
    shop_open: true,
    shop_message: "Aberto até 18h",
    ifood_available: true,
    ifood_status_label: "Recebendo pedidos",
    ifood_checked_at_display: "09:55",
    ifood_problems: [],
    diverges: false,
    ...over,
  };
}

const render = () => mount(IFoodChannelStore, { global: { stubs: { Icon: true } } });

describe("IFoodChannelStore — o que o iFood diz da loja, no card do canal", () => {
  beforeEach(() => {
    state.value = projection();
  });

  it("mostra a última conferência com o iFood", () => {
    expect(render().get("[data-ifood-status]").text()).toBe("iFood: recebendo pedidos (conferido às 09:55)");
  });

  it("não tem botão de pausa: o controle é o toggle do card, comum a todo canal", () => {
    const wrapper = render();
    expect(wrapper.find("[data-ifood-pause]").exists()).toBe(false);
    expect(wrapper.find("[data-ifood-resume]").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Pausar o iFood");
  });

  it("divergente, diz por quê", () => {
    state.value = projection({ diverges: true, ifood_available: false, ifood_problems: ["O horário gravado no iFood não cobre este instante."] });
    expect(render().get("[data-ifood-problems]").text()).toContain("O horário gravado no iFood");
  });

  it("some com a integração desligada", () => {
    state.value = projection({ enabled: false });
    expect(render().find("[data-ifood-store]").exists()).toBe(false);
  });
});
