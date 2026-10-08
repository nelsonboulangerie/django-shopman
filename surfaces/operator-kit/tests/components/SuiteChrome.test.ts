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
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, type VueWrapper } from "vue";

import OperatorLiveStatus from "../../app/components/OperatorLiveStatus.vue";
import OperatorPageHeader from "../../app/components/OperatorPageHeader.vue";
import OperatorPhoneMenu from "../../app/components/OperatorPhoneMenu.vue";
import OperatorSectionBar from "../../app/components/OperatorSectionBar.vue";
import OperatorSuiteRail from "../../app/components/OperatorSuiteRail.vue";
import type { OperatorSection } from "../../app/presentation/appBar";

const SECTIONS: OperatorSection[] = [
  {
    key: "orders",
    label: "Pedidos",
    icon: "lucide:clipboard-list",
    to: "/",
    badge: "10",
    badgeLabel: "10 pedidos na fila",
  },
  {
    key: "catalog",
    label: "Catálogo",
    icon: "lucide:book-open",
    to: "/catalog",
  },
  {
    key: "feeds",
    label: "Canais",
    icon: "lucide:monitor-play",
    to: "/feeds",
    attention: "1 desligado",
  },
];

const mounted: VueWrapper[] = [];
const stubs = {
  Icon: true,
  ClientOnly: { template: "<div><slot /></div>" },
  OperatorInbox: {
    props: ["placement"],
    template: '<div data-inbox-stub :data-placement="placement" />',
  },
};

// O rail existe nesta tela (tablet deitado/desktop) ou não (celular/tablet em pé).
const { railShown, navigate } = await vi.hoisted(async () => {
  const { ref: hoistedRef } = await import("vue");
  return { railShown: hoistedRef(true), navigate: vi.fn() };
});
mockNuxtImport("useSuiteRailShown", () => () => railShown);
mockNuxtImport("navigateTo", () => navigate);

beforeEach(() => {
  vi.stubGlobal("useColorMode", () => ({
    value: "light",
    preference: "light",
  }));
  useRailState().set("compact");
  railShown.value = true;
  navigate.mockReset();
  useOperatorShortcuts().open.value = false;
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

async function mountRail(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorSuiteRail, {
    props: {
      sections: SECTIONS,
      label: "Seções do Gestor",
      operatorName: "Ana Ferreira",
      ...props,
    },
    global: { stubs },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

describe("OperatorSuiteRail", () => {
  it("as seções do app moram no rail, com a ativa marcada para leitor de tela", async () => {
    const wrapper = await mountRail({ current: "catalog" });
    const items = wrapper.findAll("nav [data-rail-section]");
    expect(
      items.map((item) => item.attributes("aria-label")?.split(/[,:]/, 1)[0]),
    ).toEqual(["Pedidos", "Catálogo", "Canais"]);
    expect(items[1]!.attributes("aria-current")).toBe("page");
    expect(items[1]!.classes()).toContain("w-[68px]");
    expect(items[0]!.attributes("aria-current")).toBeUndefined();
  });

  it("dois andares (v4): o rótulo do grupo uma vez, e a seção do pé longe da operação", async () => {
    const wrapper = await mountRail({
      sections: [
        {
          key: "orders",
          label: "Pedidos",
          icon: "lucide:clipboard-list",
          to: "/",
          group: "Operação",
        },
        {
          key: "exit",
          label: "Saída",
          icon: "lucide:package-check",
          to: "/?columns=expedition",
          group: "Operação",
        },
        {
          key: "settings",
          label: "Ajustes",
          icon: "lucide:settings-2",
          to: "/settings",
          foot: true,
          attention: "1 desligado",
        },
      ],
      current: "settings",
    });
    const navs = wrapper.findAll("nav");
    expect(navs[0]!.findAll("[data-rail-group]").map((g) => g.text())).toEqual([
      "Operação",
    ]);
    expect(
      navs[0]!
        .findAll("[data-rail-section]")
        .map((s) => s.attributes("data-section")),
    ).toEqual(["orders", "exit"]);
    const foot = navs[1]!;
    expect(foot.attributes("aria-label")).toBe("Seções do Gestor: ajustes");
    expect(
      foot.get("[data-section='settings']").attributes("aria-current"),
    ).toBe("page");
    expect(foot.get("[data-section='settings']").attributes("aria-label")).toBe(
      "Ajustes: 1 desligado",
    );
  });

  it("o selo é visual; o que ele conta vai por extenso no nome acessível", async () => {
    const wrapper = await mountRail();
    const orders = wrapper.get("nav [data-section='orders']");
    expect(orders.get("[data-rail-badge]").attributes("aria-hidden")).toBe(
      "true",
    );
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
    expect(lock.attributes("aria-label")).toBe(
      "Ana Ferreira: travar ou trocar",
    );
    await lock.trigger("click");
    expect(wrapper.emitted("lock")).toHaveLength(1);
  });

  it("Bloquear em todo app, a Central inclusive: não há prop para escondê-lo (T-04)", async () => {
    const wrapper = await mountRail({ lockable: false });
    expect(wrapper.find("[data-rail-lock]").exists()).toBe(true);
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
      sections: [
        {
          key: "plan",
          label: "Planejamento",
          icon: "lucide:layout-grid",
          to: "/plan",
          shortcut: "Alt+1",
        },
      ],
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

  it("printShortcuts=false: a tecla só é anunciada", async () => {
    const wrapper = await mountRail({
      sections: [
        {
          key: "plan",
          label: "Planejamento",
          icon: "lucide:layout-grid",
          to: "/plan",
          shortcut: "Alt+1",
        },
      ],
      printShortcuts: false,
    });
    expect(wrapper.find("[data-rail-shortcut]").exists()).toBe(false);
  });

  it("Alt 1…9 em todo app: cada seção de cima ganha a tecla, impressa com ponteiro fino (T-05)", async () => {
    const wrapper = await mountRail();
    const keys = wrapper
      .findAll("nav [data-rail-section]")
      .map((item) => item.attributes("aria-keyshortcuts"));
    expect(keys).toEqual(["Alt+1", "Alt+2", "Alt+3"]);
    expect(
      wrapper.get("nav [data-section='catalog'] [data-rail-shortcut]").text(),
    ).toBe("Alt2");
  });

  it("Alt+N leva à seção N; com seção que não é rota, emite select", async () => {
    const wrapper = await mountRail({
      sections: [
        { key: "panel", label: "Painel", icon: "lucide:layout-dashboard" },
        { key: "buy", label: "Comprar", icon: "lucide:shopping-cart" },
        { key: "base", label: "Base", icon: "lucide:database", to: "/base" },
      ],
    });
    window.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "2",
        code: "Digit2",
        altKey: true,
        cancelable: true,
      }),
    );
    expect(wrapper.emitted("select")).toEqual([["buy"]]);
    window.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "3",
        code: "Digit3",
        altKey: true,
        cancelable: true,
      }),
    );
    expect(navigate).toHaveBeenCalledWith("/base");
  });

  it("'?' e o item Atalhos abrem a ajuda de atalhos do kit (T-02)", async () => {
    const wrapper = await mountRail();
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "?", cancelable: true }),
    );
    expect(useOperatorShortcuts().open.value).toBe(true);
    useOperatorShortcuts().open.value = false;
    const shortcuts = wrapper.get("[data-rail-shortcuts]");
    expect(shortcuts.element.parentElement!.className).toContain(
      "pointer-fine:block",
    );
    await shortcuts.trigger("click");
    expect(useOperatorShortcuts().open.value).toBe(true);
  });

  it("tablet deitado e desktop: o rail só existe com a variante rail: (no tablet em pé, barra embaixo)", async () => {
    const wrapper = await mountRail();
    const classes = wrapper.get("[data-suite-rail]").classes();
    expect(classes).toContain("hidden");
    expect(classes).toContain("rail:flex");
    expect(classes).not.toContain("md:flex");
  });

  // O pé da v4 (`_rail3bottom.html`, `gestor-fila4.html`): seções do pé, traço, UM
  // Avisos, Atalhos, Bloquear, iniciais. Sem medidor de capacidade, sem ícone de posto.
  it("o pé da v4: Ajustes · traço · Avisos · Atalhos · Bloquear · iniciais", async () => {
    const wrapper = await mountRail({
      sections: [
        {
          key: "orders",
          label: "Pedidos",
          icon: "lucide:clipboard-list",
          to: "/",
        },
        {
          key: "settings",
          label: "Ajustes",
          icon: "lucide:settings-2",
          to: "/settings",
          foot: true,
        },
      ],
    });
    const foot = wrapper.get("[data-rail-foot]");
    const html = foot.html();
    const at = (marker: string) => html.indexOf(marker);
    const order = [
      'data-section="settings"',
      "data-rail-foot-rule",
      "data-inbox-stub",
      "data-rail-shortcuts",
      "data-rail-lock",
      "data-suite-rail-menu",
    ];
    for (const marker of order) expect(at(marker), marker).toBeGreaterThan(-1);
    expect(order.map(at)).toEqual([...order.map(at)].sort((a, b) => a - b));
    expect(foot.findAll("[data-inbox-stub]")).toHaveLength(1);
    expect(wrapper.find("[data-capacity-trigger]").exists()).toBe(false);
    expect(wrapper.find("[data-rail-workstation]").exists()).toBe(false);
  });

  it("a Cozinha (inbox-first): Avisos · Ajustes · Bloquear, sem traço", async () => {
    const wrapper = await mountRail({
      sections: [
        { key: "prep", label: "Preparo", icon: "lucide:flame", to: "/" },
        {
          key: "settings",
          label: "Ajustes",
          icon: "lucide:settings-2",
          foot: true,
        },
      ],
      footOrder: "inbox-first",
    });
    const foot = wrapper.get("[data-rail-foot]");
    const html = foot.html();
    expect(html.indexOf("data-inbox-stub")).toBeLessThan(
      html.indexOf('data-section="settings"'),
    );
    expect(html.indexOf('data-section="settings"')).toBeLessThan(
      html.indexOf("data-rail-lock"),
    );
    expect(foot.find("[data-rail-foot-rule]").exists()).toBe(false);
  });

  it("onde o rail não aparece, a caixa de Avisos não é montada nele", async () => {
    railShown.value = false;
    const wrapper = await mountRail();
    expect(wrapper.find("[data-inbox-stub]").exists()).toBe(false);
  });

  it("as iniciais: alvo de 44px e fundo escuro que passa AA em todo rail", async () => {
    const wrapper = await mountRail();
    const menu = wrapper.get("[data-suite-rail-menu]");
    expect(menu.classes()).toContain("size-11");
    expect(menu.classes()).toContain("bg-black/25");
  });
});

describe("OperatorSectionBar", () => {
  it("as mesmas seções no pé, só no celular, com a ativa marcada", async () => {
    const wrapper = await mountSuspended(OperatorSectionBar, {
      props: {
        sections: SECTIONS,
        label: "Seções do Gestor",
        current: "orders",
      },
      global: { stubs },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    const nav = wrapper.get("[data-operator-section-bar]");
    expect(nav.classes()).toContain("rail:hidden");
    expect(nav.attributes("data-focus-obstruction")).toBeDefined();
    const items = nav.findAll("[data-section]");
    expect(items).toHaveLength(3);
    expect(items[0]!.attributes("aria-current")).toBe("page");
    expect(items[2]!.attributes("aria-label")).toContain("1 desligado");
  });

  it("shortLabel encurta o rótulo visível na barra e mantém o nome cheio para leitor de tela", async () => {
    const wrapper = await mountSuspended(OperatorSectionBar, {
      props: {
        sections: [
          {
            key: "plan",
            label: "Planejamento",
            shortLabel: "Plano",
            icon: "lucide:layout-grid",
            to: "/plan",
          },
          { key: "open", label: "Abertura", icon: "lucide:flame", to: "/" },
        ],
        label: "Telas de produção",
      },
      global: { stubs },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    const plan = wrapper.get('[data-section="plan"]');
    expect(plan.text()).toBe("Plano");
    expect(plan.attributes("aria-label")).toBe("Planejamento");
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

  // V6-KIT (K06/T-07/T-08): até 4 seções + "Mais", que guarda o resto e o menu do
  // operador (Bloquear, trocar de operador, tema). Sem ele o celular não trava.
  it("até 4 seções + Mais; o resto e o menu do operador moram no Mais", async () => {
    const many: OperatorSection[] = ["a", "b", "c", "d", "e", "f"].map(
      (key) => ({
        key,
        label: key.toUpperCase(),
        icon: "lucide:circle",
        to: `/${key}`,
      }),
    );
    const wrapper = await mountSuspended(OperatorSectionBar, {
      props: {
        sections: many,
        label: "Seções",
        operatorName: "Ana Ferreira",
        current: "e",
      },
      global: {
        stubs: { Icon: true, ClientOnly: { template: "<div><slot /></div>" } },
      },
      attachTo: document.body,
    });
    mounted.push(wrapper as unknown as VueWrapper);
    const nav = wrapper.get("[data-operator-section-bar]");
    expect(
      nav
        .findAll("[data-section]")
        .map((item) => item.attributes("data-section")),
    ).toEqual(["a", "b", "c", "d"]);
    const more = nav.get("[data-operator-phone-menu]");
    expect(more.text()).toContain("Mais");
    // A seção ativa mora no Mais: ele acende.
    expect(more.attributes("data-active")).toBe("true");
    await more.trigger("click");
    await nextTick();
    const sheet = document.querySelector<HTMLElement>(
      "[data-operator-phone-menu-panel]",
    )!;
    expect(
      [...sheet.querySelectorAll("[data-section]")].map((node) =>
        node.getAttribute("data-section"),
      ),
    ).toEqual(["e", "f"]);
    expect(sheet.textContent).toContain("Ana Ferreira");
    sheet.querySelector<HTMLElement>("[data-operator-menu-lock]")!.click();
    await nextTick();
    expect(wrapper.emitted("lock")).toHaveLength(1);
  });

  it("max=3 (a Cozinha, v4 do celular): três seções e o Mais", async () => {
    const four: OperatorSection[] = ["a", "b", "c", "d"].map((key) => ({
      key,
      label: key,
      icon: "lucide:circle",
      to: `/${key}`,
    }));
    const wrapper = await mountSuspended(OperatorSectionBar, {
      props: { sections: four, label: "Seções", max: 3 },
      global: { stubs },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(
      wrapper.findAll("[data-operator-section-bar] [data-section]"),
    ).toHaveLength(3);
    expect(wrapper.find("[data-operator-phone-menu]").exists()).toBe(true);
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

  it("desenha o slot #below (abas de Ajustes do PDV, prazo do Marketing)", async () => {
    const wrapper = await mountHeader({
      below: '<nav data-test-below>Terminal · Impressoras</nav>',
    });
    expect(wrapper.find("[data-test-below]").exists()).toBe(true);
  });

  it("a busca aparece uma vez; no celular a lupa pede a busca da suíte em tela cheia", async () => {
    const wrapper = await mountHeader({
      search: "<input aria-label='Buscar pedido' />",
    });
    expect(wrapper.findAll("input[aria-label='Buscar pedido']")).toHaveLength(
      1,
    );
    const box = wrapper.get("[data-page-header-search]");
    // O layout responsivo é do DashboardNavbar; a lupa abre a busca da suíte.
    expect(box.exists()).toBe(true);
    const { requests } = useSuiteSearchRequest();
    const before = requests.value;
    const toggle = wrapper.get("[data-page-header-search-toggle]");
    expect(toggle.attributes("aria-haspopup")).toBe("dialog");
    expect(toggle.attributes("aria-label")).toBe("Buscar");
    await toggle.trigger("click");
    expect(requests.value).toBe(before + 1);
  });

  it("toda tela tem a busca da suíte, mesmo sem filtro próprio (T-10/T-11)", async () => {
    const wrapper = await mountHeader();
    const box = wrapper.get("[data-page-header-search]");
    expect(box.find("[data-suite-search]").exists()).toBe(true);
    expect(wrapper.find("[data-page-header-search-toggle]").exists()).toBe(
      true,
    );
  });

  it("os controles não somem no celular: descem para uma linha que rola", async () => {
    const wrapper = await mountHeader({
      actions: "<button>Atualizar</button>",
    });
    const actions = wrapper.get("[data-page-header-actions]");
    expect(actions.classes()).not.toContain("hidden");
    expect(actions.text()).toContain("Atualizar");
  });

  it("a toolbar de recortes preserva respiro vertical ao redor das tabs", async () => {
    const wrapper = await mountHeader({ filters: "<button>Todos</button>" });
    const filters = wrapper.get("[data-page-header-filters]");
    const toolbar = filters.element.closest('[data-slot="root"]');
    expect(toolbar?.classList).toContain("py-2");
    expect(filters.classes()).toContain("w-full");
    expect(toolbar?.previousElementSibling).toBe(
      wrapper.get("[data-operator-page-header]").element,
    );
  });

  it("feedback contextual fica fora da toolbar de controles", async () => {
    const wrapper = await mountHeader({
      filters: "<button>Todos</button>",
      feedback: "<div data-warning>Canal desligado</div>",
    });
    const feedback = wrapper.get("[data-page-header-feedback]");
    expect(feedback.get("[data-warning]").text()).toBe("Canal desligado");
    expect(feedback.element.closest('[data-slot="root"]')).toBeNull();
  });

  it("onde o rail não existe, Avisos mora na barra de 56px (a caixa do kit, uma só)", async () => {
    railShown.value = false;
    const wrapper = await mountHeader();
    expect(wrapper.findAll("[data-inbox-stub]")).toHaveLength(1);
    expect(wrapper.get("[data-inbox-stub]").attributes("data-placement")).toBe(
      "header",
    );
  });

  it("onde o rail existe, a barra de 56px não monta Avisos (ele mora no rail)", async () => {
    railShown.value = true;
    const wrapper = await mountHeader();
    expect(wrapper.find("[data-inbox-stub]").exists()).toBe(false);
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
  it("ao vivo: On e a hora; o detalhe fica para o leitor de tela", async () => {
    const wrapper = await mountSuspended(OperatorLiveStatus, {
      props: { tone: "live", time: "22:03", label: "Ao vivo" },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(wrapper.text()).toContain("On 22:03");
    expect(wrapper.attributes("class")).toContain("bg-success/10");
    expect(
      wrapper.get("[data-slot='root'] > [data-slot='base']").classes(),
    ).toContain("bg-success");
    expect(
      wrapper.get("[data-slot='root'] > [data-slot='base']").classes(),
    ).toContain("h-[10px]");
    expect(wrapper.attributes("aria-label")).toContain("Ao vivo");
    expect(wrapper.attributes("aria-label")).toContain("22:03");
  });

  it("falha: Off sem hora, vermelho e com o motivo acessível", async () => {
    const wrapper = await mountSuspended(OperatorLiveStatus, {
      props: { tone: "off", time: "22:03", label: "Atualização falhou" },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(wrapper.text()).toContain("Off");
    expect(wrapper.text()).not.toContain("22:03");
    expect(wrapper.attributes("aria-label")).toContain("Atualização falhou");
    expect(wrapper.attributes("aria-label")).not.toContain("22:03");
    expect(wrapper.attributes("class")).toContain("bg-error/10");
    expect(
      wrapper.get("[data-slot='root'] > [data-slot='base']").classes(),
    ).toContain("bg-error");
    expect(wrapper.attributes("data-live-tone")).toBe("off");
  });

  it("poll automático continua On success sem alongar o cabeçalho", async () => {
    const wrapper = await mountSuspended(OperatorLiveStatus, {
      props: { tone: "calm", time: "10:30", label: "Atualiza a cada 1 min" },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(wrapper.text()).toContain("On 10:30");
    expect(wrapper.attributes("class")).toContain("bg-success/10");
    expect(
      wrapper.get("[data-slot='root'] > [data-slot='base']").classes(),
    ).toContain("bg-success");
    expect(wrapper.attributes("aria-label")).toContain("Atualiza a cada 1 min");
  });
});

// V6-KIT: onde não há barra embaixo (a Central), o menu do operador mora nas iniciais da
// barra de 56px, com Bloquear, tema e giro.
describe("OperatorPhoneMenu (header)", () => {
  async function mountMenu(props: Record<string, unknown> = {}) {
    const wrapper = await mountSuspended(OperatorPhoneMenu, {
      props: { operatorName: "Ana Ferreira", variant: "header", ...props },
      global: {
        stubs: { Icon: true, ClientOnly: { template: "<div><slot /></div>" } },
      },
      attachTo: document.body,
    });
    mounted.push(wrapper as unknown as VueWrapper);
    return wrapper;
  }

  it("só existe onde o rail não existe, com as iniciais e o nome do operador", async () => {
    const wrapper = await mountMenu();
    const trigger = wrapper.get("[data-operator-phone-menu]");
    expect(trigger.classes()).toContain("rail:hidden");
    expect(trigger.text()).toBe("AF");
    expect(trigger.attributes("aria-label")).toBe("Menu de Ana Ferreira");
  });

  it("abre com o tema e o Bloquear; Bloquear fecha o menu e emite", async () => {
    const wrapper = await mountMenu();
    await wrapper.get("[data-operator-phone-menu]").trigger("click");
    const panel = document.querySelector<HTMLElement>(
      "[data-operator-phone-menu-panel]",
    );
    expect(panel?.textContent).toContain("Tema escuro");
    document.querySelector<HTMLElement>("[data-operator-menu-lock]")!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("lock")).toHaveLength(1);
  });

  it("sem operador, sem Bloquear", async () => {
    const wrapper = await mountMenu({ operatorName: undefined });
    expect(
      wrapper.get("[data-operator-phone-menu]").attributes("aria-label"),
    ).toBe("Menu do dispositivo");
    await wrapper.get("[data-operator-phone-menu]").trigger("click");
    expect(document.querySelector("[data-operator-menu-lock]")).toBeNull();
  });
});
