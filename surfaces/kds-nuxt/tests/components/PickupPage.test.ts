import { describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref } from "vue";
import { mount } from "@vue/test-utils";

import PickupPage from "../../app/pages/pickup.vue";
import { nuxtUiStubs } from "../support/nuxtUi";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("onMounted", onMounted);
vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);

const status = ref<{ preparing: { ref: string }[]; ready: { ref: string }[] } | null>(null);
vi.stubGlobal("useKdsCustomerBoard", () => ({ status, realtime: ref("live") }));
vi.stubGlobal("usePickupCall", () => ({
  isCalling: () => false,
  calling: ref(new Set<string>()),
  soundOn: ref(false),
  soundBlocked: ref(false),
  activateSound: () => {},
}));

// O NuxtButton do painel leva `to`: o stub guarda em data-to para o teste ler.
const NuxtButton = defineComponent({
  name: "NuxtButton",
  inheritAttrs: false,
  props: { to: String, icon: String },
  setup(props, { attrs }) {
    return () => h("a", { ...attrs, "data-to": props.to });
  },
});
const passthrough = defineComponent({ setup: (_, { slots }) => () => slots.default?.() });
const stubs = { ...nuxtUiStubs, NuxtButton, Icon: true, ClientOnly: passthrough, TransitionGroup: passthrough };

const orders = (n: number) => Array.from({ length: n }, (_, i) => ({ ref: `PDV-261105-${String(i + 1).padStart(3, "0")}` }));

describe("pickup.vue", () => {
  it("tem um caminho de volta às estações (beta 05/11, KDS-10)", () => {
    status.value = { preparing: [], ready: [] };
    const w = mount(PickupPage, { global: { stubs } });
    const back = w.get("[data-kds-pickup-back]");
    expect(back.attributes("data-to")).toBe("/");
    expect(back.attributes("aria-label")).toBe("Voltar às estações");
  });

  it("a página tem a altura da tela e não rola; 24 pedidos viram grade densa com +N (beta 05/11, KDS-09)", () => {
    status.value = { preparing: orders(24), ready: orders(2) };
    const w = mount(PickupPage, { global: { stubs } });
    const root = w.get("[data-kds-pickup]");
    expect(root.classes()).toContain("h-dvh");
    expect(root.classes()).toContain("overflow-hidden");
    expect(root.classes()).not.toContain("min-h-screen");
    const prep = w.get("[data-kds-pickup-preparing]");
    expect(prep.attributes("data-density")).toBe("dense");
    expect(prep.findAll("article")).toHaveLength(17);
    expect(prep.get("[data-kds-pickup-more]").text()).toBe("+7");
  });

  it("o cartão mostra só o código, sem o prefixo da casa (beta 05/11, KDS-16)", () => {
    status.value = { preparing: [], ready: [{ ref: "PDV-261105-R09" }] };
    const w = mount(PickupPage, { global: { stubs } });
    const ready = w.get("[data-kds-pickup-ready]");
    expect(ready.text()).toContain("R09");
    expect(ready.text()).not.toContain("PDV-261105-");
  });
});
