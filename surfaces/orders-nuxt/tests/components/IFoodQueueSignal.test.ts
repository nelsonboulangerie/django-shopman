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
vi.stubGlobal("useIFoodStore", () => ({ store: state, busy: ref(false), pause: vi.fn(), resume: vi.fn(), refresh: vi.fn() }));

const stubs = {
  Icon: true,
  NuxtLink: { props: ["to"], template: "<a data-to-path :data-path='to.path' :data-focus='to.query?.focus'><slot /></a>" },
};

function projection(over: Partial<IFoodStoreProjection> = {}): IFoodStoreProjection {
  return {
    enabled: true,
    governs: true,
    can_pause: true,
    shop_open: true,
    shop_message: "Aberto até 18h",
    ifood_available: true,
    ifood_status_label: "Recebendo pedidos",
    ifood_checked_at_display: "09:55",
    ifood_problems: [],
    diverges: false,
    pause: null,
    last_pause: null,
    options: [],
    ...over,
  };
}

const activePause = {
  ref: 1, state: "active" as const, state_label: "Em vigor no iFood", reason: "Cozinha cheia",
  starts_at: "", ends_at: "", ends_at_display: "10:30", requested_by: "Ana",
  requested_at_display: "10:00", removed_by: "", error: "",
};

describe("IFoodQueueSignal — na aba Pedidos, o sinal e nunca o controle", () => {
  beforeEach(() => {
    state.value = projection();
  });

  it("em estado normal não existe", () => {
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.find("[data-ifood-signal]").exists()).toBe(false);
  });

  it("desligada, não existe nem com pausa", () => {
    state.value = projection({ enabled: false, pause: activePause });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.find("[data-ifood-signal]").exists()).toBe(false);
  });

  it("pausado, diz até quando e por quê e leva ao card do canal iFood na aba Canais", () => {
    state.value = projection({ pause: activePause });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    const link = wrapper.get("[data-ifood-signal-link]");
    expect(link.text()).toBe("iFood pausado até 10:30 — Cozinha cheia");
    expect(link.attributes("data-path")).toBe("/feeds");
    expect(link.attributes("data-focus")).toBe("ifood");
    expect(wrapper.find("[data-ifood-pause]").exists()).toBe(false);
    expect(wrapper.find("[data-ifood-resume]").exists()).toBe(false);
  });

  it("divergente, diz o lado que importa à fila", () => {
    state.value = projection({ diverges: true, ifood_available: false, ifood_status_label: "Fechado para pedidos" });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.get("[data-ifood-signal]").text()).toBe("iFood fechado com a loja aberta: nenhum pedido do iFood entra");
  });

  it("recusada, diz a recusa enquanto a janela pedida não passou", () => {
    const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    state.value = projection({ last_pause: { ...activePause, state: "failed", ends_at: future, error: "O iFood recusou o pedido (HTTP 409)." } });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.get("[data-ifood-signal]").text()).toBe("O iFood recusou a pausa pedida às 10:00");
  });

  it("quem não pode pausar lê o estado, sem link para o controle", () => {
    state.value = projection({ can_pause: false, pause: activePause });
    const wrapper = mount(IFoodQueueSignal, { global: { stubs } });
    expect(wrapper.get("[data-ifood-signal]").text()).toBe("iFood pausado até 10:30 — Cozinha cheia");
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
