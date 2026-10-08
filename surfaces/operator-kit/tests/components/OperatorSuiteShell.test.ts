// O rail da suíte em três estados (PR-K4; dono, 08/10/2026, PR #1539):
//
// - um botão só na barra do topo percorre aberto → compacto → oculto → aberto, e o
//   ícone e o nome dizem o PRÓXIMO estado; a tecla C faz o mesmo;
// - oculto = o sidebar não montado; ao voltar dele, o rail volta ABERTO, mesmo com o
//   cookie do DashboardGroup dizendo compacto;
// - sinais: ponto de estado ou número, com "Seção · estado" ou "Seção · N pendências"
//   no tooltip e no nome acessível; compacto, o chip vai no canto do ícone; aberto, o
//   mesmo chip vai na ponta direita da linha.
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "reka-ui";
import { defineComponent, h, nextTick, type VueWrapper } from "vue";

import DashboardSidebar from "@nuxt/ui/components/DashboardSidebar.vue";
import NavigationMenu from "@nuxt/ui/components/NavigationMenu.vue";
import OperatorPageHeader from "../../app/components/OperatorPageHeader.vue";
import OperatorSuiteShell from "../../app/components/OperatorSuiteShell.vue";
import type { OperatorSection } from "../../app/presentation/appBar";

const SECTIONS: OperatorSection[] = [
  { key: "orders", label: "Pedidos", icon: "i-lucide-clipboard-list", to: "/", badge: "1", badgeLabel: "1 pedido novo" },
  { key: "exit", label: "Saída", icon: "i-lucide-package-check", to: "/exit", badge: "3", tone: "error" },
  { key: "history", label: "Histórico", icon: "i-lucide-history", to: "/history", badge: "120" },
  { key: "feeds", label: "Canais", icon: "i-lucide-monitor-play", to: "/feeds", attention: "1 desligado" },
  { key: "catalog", label: "Catálogo", icon: "i-lucide-book-open", to: "/catalog" },
  { key: "settings", label: "Ajustes", icon: "i-lucide-settings", to: "/settings", foot: true },
];

const { navigate } = await vi.hoisted(async () => ({ navigate: vi.fn() }));
mockNuxtImport("navigateTo", () => navigate);

const stubs = {
  Icon: true,
  ClientOnly: { template: "<div><slot /></div>" },
  OperatorInbox: { props: ["placement"], template: '<div data-inbox-stub :data-placement="placement" />' },
  OperatorUrgentAlert: true,
  OperatorSuiteSearch: true,
};

const mounted: VueWrapper[] = [];
let storageCounter = 0;

beforeEach(() => {
  vi.stubGlobal("useColorMode", () => ({ value: "light", preference: "light" }));
  // O desktop (a partir de lg): os três estados só valem nele.
  vi.stubGlobal(
    "matchMedia",
    (query: string) => ({
      matches: /min-width:\s*1024px/.test(query) || /min-width:\s*768px/.test(query),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  );
  navigate.mockReset();
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

async function mountShell(props: Record<string, unknown> = {}) {
  // Uma chave por teste: os cookies (oculto e `{ size, collapsed }`) não vazam.
  storageCounter += 1;
  const shellProps = {
    storageKey: `shell-test-${storageCounter}`,
    sections: SECTIONS,
    label: "Seções do Gestor",
    operatorName: "Ana Ferreira",
    ...props,
  };
  // O app monta o `NuxtApp` (TooltipProvider); aqui, só o provider do Reka.
  const Host = defineComponent({
    setup: () => () =>
      h(TooltipProvider, null, () =>
        h(OperatorSuiteShell, shellProps, {
          default: () => h(OperatorPageHeader, { title: "Pedidos" }),
        }),
      ),
  });
  const wrapper = await mountSuspended(Host, { global: { stubs } });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

async function settle() {
  await nextTick();
  await nextTick();
  await nextTick();
}

function railState(wrapper: Awaited<ReturnType<typeof mountShell>>) {
  return wrapper.get("[data-operator-suite-shell]").attributes("data-rail-state");
}

function railLinks(wrapper: Awaited<ReturnType<typeof mountShell>>) {
  return wrapper.findAll("[data-suite-rail-navigation] [data-section]");
}

describe("OperatorSuiteShell: os três estados", () => {
  it("o botão da barra percorre aberto → compacto → oculto → aberto e diz o próximo", async () => {
    const wrapper = await mountShell();
    const cycle = () => wrapper.get("[data-rail-cycle]");

    expect(railState(wrapper)).toBe("open");
    expect(cycle().attributes("aria-label")).toBe("Compactar o rail");
    expect(wrapper.get("[data-suite-rail]").attributes("data-collapsed")).toBe("false");

    await cycle().trigger("click");
    await settle();
    expect(railState(wrapper)).toBe("compact");
    expect(cycle().attributes("aria-label")).toBe("Ocultar o rail");
    expect(wrapper.get("[data-suite-rail]").attributes("data-collapsed")).toBe("true");

    await cycle().trigger("click");
    await settle();
    expect(railState(wrapper)).toBe("hidden");
    expect(cycle().attributes("aria-label")).toBe("Mostrar o rail");
    // Oculto é o sidebar não montado.
    expect(wrapper.find("[data-suite-rail]").exists()).toBe(false);
    // Sem o rail na tela, Avisos sobe para a barra do topo.
    expect(wrapper.get("[data-inbox-stub]").attributes("data-placement")).toBe("header");

    await cycle().trigger("click");
    await settle();
    expect(cycle().attributes("aria-label")).toBe("Compactar o rail");
    expect(railState(wrapper)).toBe("open");
  });

  it("volta do oculto para ABERTO, mesmo com o cookie do sidebar dizendo compacto", async () => {
    const wrapper = await mountShell();
    await wrapper.get("[data-rail-cycle]").trigger("click"); // compacto (gravado no cookie)
    await settle();
    await wrapper.get("[data-rail-cycle]").trigger("click"); // oculto
    await settle();
    await wrapper.get("[data-rail-cycle]").trigger("click"); // aberto
    await settle();
    expect(wrapper.get("[data-suite-rail]").attributes("data-collapsed")).toBe("false");
    expect(railState(wrapper)).toBe("open");
    // E o rail aberto diz o nome das seções.
    expect(wrapper.get("[data-suite-rail-navigation]").text()).toContain("Pedidos");
  });

  it("a tecla C faz o mesmo percurso", async () => {
    const wrapper = await mountShell();
    const press = async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "c", code: "KeyC", cancelable: true }));
      await settle();
    };
    await press();
    expect(railState(wrapper)).toBe("compact");
    await press();
    expect(railState(wrapper)).toBe("hidden");
    await press();
    expect(railState(wrapper)).toBe("open");
  });

  it("a ajuda de atalhos ensina a tecla C", async () => {
    const wrapper = await mountShell();
    expect(wrapper.findComponent({ name: "OperatorShortcutsHelp" }).props("rail")).toBe(true);
  });

  it("o rail é das peças oficiais, sem :ui por instância", async () => {
    const wrapper = await mountShell();
    const sidebar = wrapper.findComponent(DashboardSidebar);
    expect(sidebar.props()).toMatchObject({
      collapsible: true,
      resizable: true,
      collapsedSize: 4,
      minSize: 12,
      maxSize: 20,
    });
    expect(sidebar.props("ui")).toBeUndefined();
    const menu = wrapper.findComponent(NavigationMenu);
    expect(menu.props()).toMatchObject({ orientation: "vertical", tooltip: true, popover: true });
  });
});

describe("OperatorSuiteShell: os sinais", () => {
  it("tooltip e nome acessível: 'Seção · estado' ou 'Seção · N pendências'", async () => {
    const wrapper = await mountShell();
    expect(railLinks(wrapper).map((link) => link.attributes("aria-label"))).toEqual([
      "Pedidos · 1 pendência",
      "Saída · 3 pendências",
      "Histórico · 120 pendências",
      "Canais · 1 desligado",
      "Catálogo",
    ]);
  });

  it("aberto: o chip vai na ponta direita da linha, com '99+' acima de 99", async () => {
    const wrapper = await mountShell();
    const trailing = wrapper.findAll('[data-suite-rail-navigation] [data-slot="linkTrailing"] [data-slot="base"]');
    expect(trailing).toHaveLength(4);
    expect(trailing.map((chip) => chip.text())).toEqual(["1", "3", "99+", ""]);
    expect(wrapper.find('[data-suite-rail-navigation] [data-slot="linkLeadingChip"]').exists()).toBe(false);
  });

  it("compacto: o mesmo chip vai no canto do ícone, e nada no fim da linha", async () => {
    const wrapper = await mountShell();
    await wrapper.get("[data-rail-cycle]").trigger("click");
    await settle();
    expect(wrapper.find('[data-suite-rail-navigation] [data-slot="linkTrailing"] [data-slot="base"]').exists()).toBe(false);
    const corner = wrapper.findAll('[data-suite-rail-navigation] [data-slot="linkLeadingChip"]');
    expect(corner).toHaveLength(4);
    expect(corner.map((chip) => chip.text())).toEqual(["1", "3", "99+", ""]);
    // O nome acessível não muda com o estado.
    expect(railLinks(wrapper)[1]!.attributes("aria-label")).toBe("Saída · 3 pendências");
  });

  it("a seção ativa é marcada para leitor de tela", async () => {
    const wrapper = await mountShell({ current: "feeds" });
    const links = railLinks(wrapper);
    expect(links[3]!.attributes("aria-current")).toBe("page");
    expect(links[0]!.attributes("aria-current")).toBeUndefined();
  });
});

describe("OperatorSuiteShell: o que o shell já fazia", () => {
  it("o pé: seção do pé, Atalhos só com ponteiro fino, Bloquear, Avisos e o operador", async () => {
    const wrapper = await mountShell();
    const footer = wrapper.get("[data-suite-rail-footer]");
    expect(footer.find('[data-section="settings"]').exists()).toBe(true);
    expect(footer.get("[data-rail-shortcuts]").classes()).toContain("pointer-fine:flex");
    expect(footer.find("[data-inbox-stub]").attributes("data-placement")).toBe("rail");
    await footer.get("[data-rail-lock]").trigger("click");
    expect(wrapper.findComponent(OperatorSuiteShell).emitted("lock")).toHaveLength(1);
    expect(footer.find("[data-suite-rail-menu]").exists()).toBe(true);
  });

  it("sem operador, sem Bloquear e sem menu do operador", async () => {
    const wrapper = await mountShell({ operatorName: undefined });
    expect(wrapper.find("[data-rail-lock]").exists()).toBe(false);
    expect(wrapper.find("[data-suite-rail-menu]").exists()).toBe(false);
  });

  it("Alt+N leva à seção N; '?' abre a ajuda de atalhos", async () => {
    await mountShell();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "2", code: "Digit2", altKey: true, cancelable: true }));
    expect(navigate).toHaveBeenCalledWith("/exit");
    useOperatorShortcuts().open.value = false;
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "?", code: "Slash", shiftKey: true, cancelable: true }));
    expect(useOperatorShortcuts().open.value).toBe(true);
    useOperatorShortcuts().open.value = false;
  });

  it("a barra de seções do polegar continua embaixo, abaixo de lg", async () => {
    const wrapper = await mountShell();
    const tabs = wrapper.get("[data-operator-suite-tabs]");
    expect(tabs.classes()).toContain("lg:hidden");
  });
});
