// A peça da busca da suíte (V6-BUSCA; SUITE-UX-V2 §2.2, prévias v3 `depois-gestor-busca`
// e `depois-hub-celular`). O que se trava aqui:
//
// - o campo filtra a tela (v-model) enquanto se digita e abre o painel com o alcance;
// - os resultados da suíte chegam agrupados por tipo, como links para o app de destino;
// - teclado: ↑↓ anda (aria-activedescendant), Tab troca o alcance, Esc fecha e MANTÉM o filtro;
// - "/" e Ctrl K abrem de qualquer lugar da tela; a lupa do cabeçalho pede a busca;
// - a variante `hotkey` (Venda do PDV) não põe campo na tela e abre num diálogo;
// - acessível: combobox + listbox, opções com nome que diz o que é e onde abre.
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { DOMWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import type { VueWrapper } from "@vue/test-utils";

import OperatorSuiteSearch from "../../app/components/OperatorSuiteSearch.vue";

const RESPONSE = {
  search: {
    query: "maria",
    searched: true,
    total: 3,
    groups: [
      {
        type: "orders",
        label: "Pedidos",
        results: [
          { key: "order:X36", type: "orders", app: "gestor", app_label: "Gestor", place: "Gestor › Pedidos", title: "X36 · Maria Santos", detail: "Em preparo", url: "https://gestor.test/X36", icon: "clipboard-list" },
        ],
      },
      {
        type: "customers",
        label: "Clientes",
        results: [
          { key: "customer:C1", type: "customers", app: "gestor", app_label: "Gestor", place: "Gestor › Clientes", title: "Maria Santos", detail: "23 pedidos", url: "https://gestor.test/customers/C1", icon: "user" },
        ],
      },
      {
        type: "preorders",
        label: "Encomendas",
        results: [
          { key: "preorder:X36", type: "preorders", app: "pos", app_label: "PDV", place: "PDV › Encomendas", title: "Encomenda de Maria Santos", detail: "Retirada hoje", url: "https://pdv.test/preorders/X36", icon: "calendar-clock" },
        ],
      },
    ],
    apps: [
      { ref: "gestor", label: "Gestor", count: 2 },
      { ref: "pos", label: "PDV", count: 1 },
    ],
  },
};

const mounted: VueWrapper[] = [];
const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(RESPONSE);
  const config = useRuntimeConfig().public as Record<string, unknown>;
  config.operatorPwa = { app: "orders", identity: { label: "Gestor de pedidos" } };
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

async function mountSearch(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorSuiteSearch, {
    props: { placeholder: "Buscar pedido, cliente ou item", ...props },
    global: { stubs: { Icon: true } },
    attachTo: document.body,
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

async function settle() {
  await vi.advanceTimersByTimeAsync(400);
  await nextTick();
  await nextTick();
}

const dom = (selector: string) => new DOMWrapper(document.querySelector(selector) as Element);
const commandInput = () => dom("[data-suite-search-panel] input");
const tabLabels = (selector: string) => dom(selector).findAll('[role="tab"]').map((tab) => tab.text());
async function activateTab(selector: string, index: number) {
  const tab = dom(selector).findAll('[role="tab"]')[index]!;
  tab.element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
  (tab.element as HTMLElement).click();
  await nextTick();
}

async function openSearch(wrapper: VueWrapper) {
  await wrapper.get("[data-suite-search-input]").trigger("click");
  await nextTick();
  await nextTick();
  return commandInput();
}

describe("OperatorSuiteSearch", () => {
  it("digitar filtra a tela e abre o painel com o alcance e a suíte por tipo", async () => {
    const wrapper = await mountSearch({ modelValue: "", screenLabel: "filtrando o quadro", "onUpdate:modelValue": () => {} });
    const input = await openSearch(wrapper);
    expect(input.attributes("type")).toBe("text");
    await input.setValue("maria");
    expect(wrapper.emitted("update:modelValue")!.at(-1)).toEqual(["maria"]);
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]![1]).toEqual({ query: { q: "maria" } });

    const panel = dom("[data-suite-search-panel]");
    const scopes = dom("[data-suite-search-scopes]").findAll('[role="tab"]');
    expect(scopes.map((s) => s.text())).toEqual(["Esta tela", "Gestor · 2", "Toda a suíte · 3"]);
    expect(document.body.textContent).toContain("filtrando o quadro");
    expect(panel.text()).toContain("Pedidos");
    expect(panel.text()).toContain("Clientes");
    expect(panel.text()).toContain("Encomendas");
    const results = panel.findAll("[data-suite-search-result]");
    expect(results.map((r) => r.attributes("href"))).toEqual([
      "https://gestor.test/X36",
      "https://gestor.test/customers/C1",
      "https://pdv.test/preorders/X36",
    ]);
    expect(results[0]!.attributes("role")).toBe("option");
    expect(results[0]!.attributes("aria-label")).toBe("X36 · Maria Santos, Gestor › Pedidos, Em preparo");
  });

  it("as Tabs canônicas trocam o alcance e o App recorta pelo app atual", async () => {
    const wrapper = await mountSearch();
    const input = await openSearch(wrapper);
    await input.setValue("maria");
    await settle();
    expect(tabLabels("[data-suite-search-scopes]")).toEqual(["Gestor · 2", "Toda a suíte · 3"]);
    expect(document.querySelectorAll("[data-suite-search-result]")).toHaveLength(2);
    await activateTab("[data-suite-search-scopes]", 1);
    expect(document.querySelectorAll("[data-suite-search-result]")).toHaveLength(3);
  });

  it("o CommandPalette navega por teclado e Esc fecha mantendo o filtro", async () => {
    const wrapper = await mountSearch({ modelValue: "", "onUpdate:modelValue": () => {} });
    const input = await openSearch(wrapper);
    await input.setValue("maria");
    await settle();
    await input.trigger("keydown", { key: "ArrowDown" });
    const activeId = input.attributes("aria-activedescendant");
    expect(activeId).toBeTruthy();
    expect(document.getElementById(activeId!)).not.toBeNull();
    await input.trigger("keydown", { key: "Escape" });
    await nextTick();
    expect(document.querySelector("[data-suite-search-dialog]")).toBeNull();
    expect(wrapper.get("[data-suite-search-input]").text()).toContain("maria");
    expect(wrapper.emitted("update:modelValue")!.some((e) => e[0] === "")).toBe(false);
  });

  it("termo curto não vai ao servidor e diz o que falta", async () => {
    const wrapper = await mountSearch();
    const input = await openSearch(wrapper);
    await input.setValue("m");
    await settle();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(dom("[data-suite-search-hint]").text()).toContain("Digite pelo menos 2 letras para buscar na suíte.");
  });

  it("a suíte fora do ar não apaga o filtro da tela", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    const wrapper = await mountSearch({ modelValue: "", "onUpdate:modelValue": () => {} });
    await (await openSearch(wrapper)).setValue("maria");
    await settle();
    expect(dom("[data-suite-search-error]").text()).toContain("O filtro desta tela continua valendo.");
  });

  it("`/` e Ctrl K abrem a busca canônica de qualquer lugar da tela", async () => {
    await mountSearch();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true }));
    await nextTick();
    await nextTick();
    expect(document.querySelector("[data-suite-search-dialog]")).not.toBeNull();
    commandInput().element.blur();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await nextTick();
    const ctrlK = new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true, cancelable: true });
    window.dispatchEvent(ctrlK);
    await nextTick();
    expect(ctrlK.defaultPrevented).toBe(true);
    expect(document.querySelector("[data-suite-search-dialog]")).not.toBeNull();
  });

  it("o DashboardSearchButton expõe o atalho com Kbd canônico", async () => {
    const wrapper = await mountSearch();
    expect(wrapper.get("kbd").text()).toBe("/");
  });

  it("a lupa do cabeçalho pede a busca, e a variante `hotkey` abre num diálogo sem campo na tela", async () => {
    const wrapper = await mountSearch({ variant: "hotkey" });
    expect(wrapper.find("[data-suite-search-input]").exists()).toBe(false);
    // `/` é do campo da tela (PDV): não abre a suíte.
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true }));
    await nextTick();
    expect(document.querySelector("[data-suite-search-dialog]")).toBeNull();
    useSuiteSearchRequest().request();
    await nextTick();
    await nextTick();
    const dialog = document.querySelector<HTMLElement>("[data-suite-search-dialog]")!;
    const modal = dialog.closest('[role="dialog"]')!;
    expect(modal.getAttribute("role")).toBe("dialog");
    const input = commandInput();
    await input.setValue("maria");
    await settle();
    expect([...dialog.querySelectorAll("[data-suite-search-result]")].map((a) => a.getAttribute("href"))).toEqual(["https://gestor.test/X36", "https://gestor.test/customers/C1"]);
    // Os chips: o alcance (o App primeiro, sem filtro de tela) e, depois, os tipos dele.
    expect(tabLabels("[data-suite-search-scopes]")).toEqual(["Gestor · 2", "Toda a suíte · 3"]);
    expect(tabLabels("[data-suite-search-chips]")).toEqual(["Todos", "Pedidos · 1", "Clientes · 1"]);
    await input.trigger("keydown", { key: "Escape" });
    await nextTick();
    expect(document.querySelector("[data-suite-search-dialog]")).toBeNull();
  });
});
