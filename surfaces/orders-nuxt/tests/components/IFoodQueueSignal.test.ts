import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import IFoodQueueSignal from "../../app/components/IFoodQueueSignal.vue";
import type { IFoodStoreProjection } from "../../app/types/ifoodStore";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);

const state = ref<IFoodStoreProjection | null>(null);
vi.stubGlobal("useIFoodStore", () => ({ store: state, refresh: vi.fn() }));

const stubs = {
  Icon: true,
  NuxtLink: { props: ["to"], template: "<a data-to-path :data-path='to.path' :data-focus='to.query?.focus'><slot /></a>" },
};

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

describe("IFoodQueueSignal — na aba Pedidos, o sinal e nunca o controle", () => {
  beforeEach(() => {
    state.value = projection();
  });

  it("em estado normal não existe", () => {
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.find("[data-ifood-signal]").exists()).toBe(false);
  });

  it("integração desligada, não existe nem com o canal desligado", () => {
    state.value = projection({ enabled: false, channel_off: true });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.find("[data-ifood-signal]").exists()).toBe(false);
  });

  it("canal desligado no Gestor: diz que nenhum pedido do iFood entra e leva ao card", () => {
    state.value = projection({ channel_off: true });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    const link = wrapper.get("[data-ifood-signal-link]");
    expect(link.text()).toBe("iFood desligado no Gestor: nenhum pedido do iFood entra");
    expect(link.attributes("data-path")).toBe("/feeds");
    expect(link.attributes("data-focus")).toBe("ifood");
  });

  it("divergente, diz o lado que importa à fila", () => {
    state.value = projection({ diverges: true, ifood_available: false, ifood_status_label: "Fechado para pedidos" });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.get("[data-ifood-signal]").text()).toBe("iFood fechado com a loja aberta: nenhum pedido do iFood entra");
  });

  it("quem não abre a aba Canais lê o estado, sem link para o controle", () => {
    state.value = projection({ can_open_channels: false, channel_off: true });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.get("[data-ifood-signal]").text()).toBe("iFood desligado no Gestor: nenhum pedido do iFood entra");
    expect(wrapper.find("[data-ifood-signal-link]").exists()).toBe(false);
  });
});

describe("a aba Pedidos não carrega o controle do canal", () => {
  const page = readFileSync(resolve(__dirname, "../../app/pages/index.vue"), "utf8");

  it("sem o ⋮ de mais opções na barra; só o sinal", () => {
    expect(page).not.toContain("IFoodStoreMenu");
    expect(page).not.toContain("IFoodChannelStore");
    expect(page).not.toContain("Mais opções");
    expect(page).toContain("<IFoodQueueSignal />");
  });
});
