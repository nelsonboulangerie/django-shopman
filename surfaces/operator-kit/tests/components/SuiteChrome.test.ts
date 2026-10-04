// Camada visual da suíte (UX-KIT-V1): o contrato das peças novas do chrome.
//
// - `OperatorSuiteRail`: as seções do app moram no rail (tablet e desktop), com a ativa
//   marcada para leitor de tela, selo de contagem, ponto de atenção que entra no nome
//   acessível, Bloquear e o menu do operador; colapsado, o rail some de verdade.
// - `OperatorSectionBar`: as mesmas seções na barra do polegar (celular).
// - `OperatorPageHeader`: o título é o `h1` da tela; a busca aparece uma vez só; com o
//   rail oculto, o cabeçalho oferece o caminho de volta para ele.
// - `OperatorLiveStatus`: "ao vivo" é só o ponto e a hora; qualquer outro estado se
//   escreve por extenso (a cor nunca fala sozinha).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { VueWrapper } from "vue";

import OperatorLiveStatus from "../../app/components/OperatorLiveStatus.vue";
import OperatorPageHeader from "../../app/components/OperatorPageHeader.vue";
import OperatorSectionBar from "../../app/components/OperatorSectionBar.vue";
import OperatorSuiteRail from "../../app/components/OperatorSuiteRail.vue";
import type { OperatorSection } from "../../app/presentation/appBar";

const SECTIONS: OperatorSection[] = [
  { key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: "/", badge: "10", badgeLabel: "10 pedidos na fila" },
  { key: "catalog", label: "Catálogo", icon: "lucide:book-open", to: "/catalog" },
  { key: "feeds", label: "Canais", icon: "lucide:monitor-play", to: "/feeds", attention: "1 desligado" },
];

const mounted: VueWrapper[] = [];
const stubs = { Icon: true, ClientOnly: true, OperatorCapacityStatus: true };

beforeEach(() => {
  vi.stubGlobal("useColorMode", () => ({ value: "light", preference: "light" }));
  useRailState().set("compact");
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

async function mountRail(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorSuiteRail, {
    props: { sections: SECTIONS, label: "Seções do Gestor", operatorName: "Ana Ferreira", ...props },
    global: { stubs },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

describe("OperatorSuiteRail", () => {
  it("as seções do app moram no rail, com a ativa marcada para leitor de tela", async () => {
    const wrapper = await mountRail({ current: "catalog" });
    const items = wrapper.findAll("nav [data-rail-section]");
    expect(items.map((item) => item.text())).toEqual(["Pedidos10", "Catálogo", "Canais"]);
    expect(items[1]!.attributes("aria-current")).toBe("page");
    expect(items[0]!.attributes("aria-current")).toBeUndefined();
  });

  it("dois andares (v4): o rótulo do grupo uma vez, e a seção do pé longe da operação", async () => {
    const wrapper = await mountRail({
      sections: [
        { key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: "/", group: "Operação" },
        { key: "exit", label: "Saída", icon: "lucide:package-check", to: "/?columns=expedition", group: "Operação" },
        { key: "settings", label: "Ajustes", icon: "lucide:settings-2", to: "/settings", foot: true, attention: "1 desligado" },
      ],
      current: "settings",
    });
    const navs = wrapper.findAll("nav");
    expect(navs[0]!.findAll("[data-rail-group]").map((g) => g.text())).toEqual(["Operação"]);
    expect(navs[0]!.findAll("[data-rail-section]").map((s) => s.attributes("data-section"))).toEqual(["orders", "exit"]);
    const foot = navs[1]!;
    expect(foot.attributes("aria-label")).toBe("Seções do Gestor: ajustes");
    expect(foot.get("[data-section='settings']").attributes("aria-current")).toBe("page");
    expect(foot.get("[data-section='settings']").attributes("aria-label")).toBe("Ajustes: 1 desligado");
  });

  it("o selo é visual; o que ele conta vai por extenso no nome acessível", async () => {
    const wrapper = await mountRail();
    const orders = wrapper.get("nav [data-section='orders']");
    expect(orders.get("[data-rail-badge]").attributes("aria-hidden")).toBe("true");
    expect(orders.attributes("aria-label")).toBe("Pedidos, 10 pedidos na fila");
  });

  it("a atenção vira um ponto no ícone e entra no nome acessível", async () => {
    const wrapper = await mountRail();
    const feeds = wrapper.get("nav [data-section='feeds']");
    expect(feeds.find("[data-rail-attention]").exists()).toBe(true);
    expect(feeds.attributes("aria-label")).toBe("Canais: 1 desligado");
  });

  it("Bloquear emite lock, com o nome de quem sai", async () => {
    const wrapper = await mountRail();
    const lock = wrapper.get("[data-rail-lock]");
    expect(lock.attributes("aria-label")).toBe("Ana Ferreira: travar ou trocar");
    await lock.trigger("click");
    expect(wrapper.emitted("lock")).toHaveLength(1);
  });

  it("lockable=false (a Central): sem Bloquear, e as iniciais seguem no pé", async () => {
    const wrapper = await mountRail({ lockable: false });
    expect(wrapper.find("[data-rail-lock]").exists()).toBe(false);
    expect(wrapper.get("[data-suite-rail-menu]").text()).toBe("AF");
  });

  it("o menu do operador mostra as iniciais", async () => {
    const wrapper = await mountRail();
    expect(wrapper.get("[data-suite-rail-menu]").text()).toBe("AF");
  });

  it("o selo do app leva à Central quando há hubUrl", async () => {
    const wrapper = await mountRail({ hubUrl: "http://central/" });
    const app = wrapper.get("[data-suite-rail-app]");
    expect(app.element.tagName).toBe("A");
    expect(app.attributes("href")).toBe("http://central/");
  });

  it("colapsado, o rail some de verdade", async () => {
    useRailState().set("collapsed");
    const wrapper = await mountRail();
    expect(wrapper.find("[data-suite-rail]").exists()).toBe(false);
  });

  // V4-PROD (prévia `plano-porque4.html`): a Produção imprime a tecla sob o nome (só
  // com ponteiro fino) e usa rótulos de 10px para "Planejamento". Opt-in: sem as
  // props, nada muda (o primeiro teste acima continua sem a tecla no texto).
  it("printShortcuts imprime a tecla da seção, sem o +, e denseLabels aperta o rótulo", async () => {
    const wrapper = await mountRail({
      sections: [{ key: "plan", label: "Planejamento", icon: "lucide:layout-grid", to: "/plan", shortcut: "Alt+1" }],
      printShortcuts: true,
      denseLabels: true,
    });
    const item = wrapper.get('nav [data-section="plan"]');
    const kbd = item.get("[data-rail-shortcut]");
    expect(kbd.text()).toBe("Alt1");
    expect(kbd.classes()).toContain("pointer-fine:block");
    expect(kbd.attributes("aria-hidden")).toBe("true");
    expect(item.attributes("aria-keyshortcuts")).toBe("Alt+1");
    expect(item.classes()).toContain("text-[10px]");
  });

  it("sem printShortcuts a tecla só é anunciada", async () => {
    const wrapper = await mountRail({
      sections: [{ key: "plan", label: "Planejamento", icon: "lucide:layout-grid", to: "/plan", shortcut: "Alt+1" }],
    });
    expect(wrapper.find("[data-rail-shortcut]").exists()).toBe(false);
  });

  it("do tablet para cima: o rail não existe abaixo de md", async () => {
    const wrapper = await mountRail();
    const classes = wrapper.get("[data-suite-rail]").classes();
    expect(classes).toContain("hidden");
    expect(classes).toContain("md:flex");
  });
});

describe("OperatorSectionBar", () => {
  it("as mesmas seções no pé, só no celular, com a ativa marcada", async () => {
    const wrapper = await mountSuspended(OperatorSectionBar, {
      props: { sections: SECTIONS, label: "Seções do Gestor", current: "orders" },
      global: { stubs },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    const nav = wrapper.get("[data-operator-section-bar]");
    expect(nav.classes()).toContain("md:hidden");
    expect(nav.attributes("data-focus-obstruction")).toBeDefined();
    const items = nav.findAll("[data-section]");
    expect(items).toHaveLength(3);
    expect(items[0]!.attributes("aria-current")).toBe("page");
    expect(items[2]!.text()).toContain("1 desligado");
  });

  it("shortLabel encurta o rótulo visível na barra e mantém o nome cheio para leitor de tela", async () => {
    const wrapper = await mountSuspended(OperatorSectionBar, {
      props: {
        sections: [
          { key: "plan", label: "Planejamento", shortLabel: "Plano", icon: "lucide:layout-grid", to: "/plan" },
          { key: "open", label: "Abertura", icon: "lucide:flame", to: "/" },
        ],
        label: "Telas de produção",
      },
      global: { stubs },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    const plan = wrapper.get('[data-section="plan"]');
    expect(plan.get("[data-section-short]").text()).toBe("Plano");
    expect(plan.get(".sr-only").text()).toBe("Planejamento");
    expect(wrapper.get('[data-section="open"]').text()).toBe("Abertura");
  });

  it("uma seção só não vira barra", async () => {
    const wrapper = await mountSuspended(OperatorSectionBar, {
      props: { sections: SECTIONS.slice(0, 1), label: "Seções do Gestor" },
      global: { stubs },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(wrapper.find("[data-operator-section-bar]").exists()).toBe(false);
  });
});

describe("OperatorPageHeader", () => {
  async function mountHeader(slots: Record<string, string> = {}) {
    const wrapper = await mountSuspended(OperatorPageHeader, {
      props: { title: "Pedidos" },
      slots,
      global: { stubs },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    return wrapper;
  }

  it("o título é o h1 da tela", async () => {
    const wrapper = await mountHeader();
    expect(wrapper.get("h1").text()).toBe("Pedidos");
  });

  it("a busca aparece uma vez; no celular a lupa a abre numa linha própria", async () => {
    const wrapper = await mountHeader({ search: "<input aria-label='Buscar pedido' />" });
    expect(wrapper.findAll("input[aria-label='Buscar pedido']")).toHaveLength(1);
    const box = wrapper.get("[data-page-header-search]");
    expect(box.classes()).toContain("hidden");
    await wrapper.get("[data-page-header-search-toggle]").trigger("click");
    expect(box.classes()).not.toContain("hidden");
    expect(wrapper.get("[data-page-header-search-toggle]").attributes("aria-expanded")).toBe("true");
  });

  it("os controles não somem no celular: descem para uma linha que rola", async () => {
    const wrapper = await mountHeader({ actions: "<button>Atualizar</button>" });
    const actions = wrapper.get("[data-page-header-actions]");
    expect(actions.classes()).not.toContain("hidden");
    expect(actions.classes()).toContain("overflow-x-auto");
  });

  it("com o rail oculto, o cabeçalho oferece o caminho de volta", async () => {
    useRailState().set("collapsed");
    const wrapper = await mountHeader();
    const show = wrapper.get("[data-page-header-show-rail]");
    await show.trigger("click");
    expect(useRailState().state.value).toBe("compact");
  });
});

describe("OperatorLiveStatus", () => {
  it("ao vivo: o ponto e a hora; o rótulo fica para o leitor de tela", async () => {
    const wrapper = await mountSuspended(OperatorLiveStatus, { props: { tone: "live", time: "22:03", label: "Ao vivo" } });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(wrapper.text()).toBe("22:03");
    expect(wrapper.attributes("aria-label")).toContain("Ao vivo");
    expect(wrapper.attributes("aria-label")).toContain("22:03");
  });

  it("fora do ao vivo, o estado se escreve por extenso", async () => {
    const wrapper = await mountSuspended(OperatorLiveStatus, { props: { tone: "off", time: "22:03", label: "Atualização falhou" } });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(wrapper.text()).toContain("Atualização falhou");
    expect(wrapper.attributes("data-live-tone")).toBe("off");
  });
});
