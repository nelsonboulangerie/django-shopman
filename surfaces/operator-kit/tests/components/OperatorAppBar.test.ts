// A barra de seções canônica. O que este teste trava é o que a medição de 22/09/2026
// mostrou divergindo entre os quatro apps que a escreviam à mão: alvo de toque,
// `aria-current`, o aviso de atenção e a tecla ensinada na própria aba.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import type { VueWrapper } from "vue";

import OperatorAppBar from "../../app/components/OperatorAppBar.vue";
import type { OperatorSection } from "../../app/presentation/appBar";

const SECTIONS: OperatorSection[] = [
  { key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: "/" },
  { key: "catalog", label: "Catálogo", icon: "lucide:book-open", to: "/catalog", shortcut: "Alt+2" },
  { key: "feeds", label: "Canais", icon: "lucide:monitor-play", to: "/feeds", attention: "1 desligado" },
];

const mounted: VueWrapper[] = [];

async function mountBar(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorAppBar, {
    props: { sections: SECTIONS, label: "Seções do Gestor", path: "/catalog", ...props },
    global: { stubs: { Icon: true, OperatorKbd: false } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("OperatorAppBar", () => {
  it("toda aba tem o alvo de toque da casa", async () => {
    // O B.I. e o Compras estavam em `h-8` — metade do token `--spacing-control`, numa
    // barra que se usa com a mão ocupada.
    const wrapper = await mountBar();
    const tabs = wrapper.findAll("[data-section]");
    expect(tabs).toHaveLength(3);
    for (const tab of tabs) expect(tab.classes()).toContain("min-h-control");
  });

  it("a aba ativa se anuncia para quem não vê a tela", async () => {
    const wrapper = await mountBar();
    expect(wrapper.get('[data-section="catalog"]').attributes("aria-current")).toBe("page");
    expect(wrapper.get('[data-section="orders"]').attributes("aria-current")).toBeUndefined();
    expect(wrapper.get('[data-section="catalog"]').attributes("data-active")).toBe("true");
  });

  it("a rota filha mantém a seção da mãe acesa", async () => {
    const wrapper = await mountBar({ path: "/catalog/PAO-001" });
    expect(wrapper.get('[data-section="catalog"]').attributes("data-active")).toBe("true");
  });

  it("atenção só aparece quando há atenção", async () => {
    const wrapper = await mountBar();
    expect(wrapper.find('[data-attention="feeds"]').text()).toContain("1 desligado");
    expect(wrapper.find('[data-attention="orders"]').exists()).toBe(false);
  });

  it("a tecla é ensinada na aba e anunciada no atributo", async () => {
    const wrapper = await mountBar();
    const tab = wrapper.get('[data-section="catalog"]');
    expect(tab.attributes("aria-keyshortcuts")).toBe("Alt+2");
    expect(tab.text()).toContain("Alt+2");
  });

  it("seção sem rota vira botão e devolve a escolha ao app", async () => {
    // O Compras não navega: a seção dele é estado (`useState("purchase-view")`).
    const estado: OperatorSection[] = [
      { key: "panel", label: "Painel", icon: "lucide:layout-dashboard" },
      { key: "buy", label: "Comprar", icon: "lucide:shopping-cart" },
    ];
    const wrapper = await mountBar({ sections: estado, current: "panel", path: undefined });

    expect(wrapper.get('[data-section="panel"]').attributes("data-active")).toBe("true");
    await wrapper.get('[data-section="buy"]').trigger("click");
    expect(wrapper.emitted("select")).toEqual([["buy"]]);
  });

  it("o controle do rail está sempre na barra, e a nav tem nome", async () => {
    const wrapper = await mountBar();
    expect(wrapper.findComponent({ name: "RailToggle" }).exists()).toBe(true);
    expect(wrapper.get("nav").attributes("aria-label")).toBe("Seções do Gestor");
  });
});
