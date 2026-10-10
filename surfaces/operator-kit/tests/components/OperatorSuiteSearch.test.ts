// A busca da suíte em níveis (V6-BUSCA; fase 2, K6: "busca em níveis no canônico", dono
// 09/10/2026). O que se trava aqui:
//
// - o painel é o `NuxtDashboardSearch` oficial, aberto pelo `NuxtDashboardSearchButton`;
// - os níveis são os grupos do painel em ordem fixa: Nesta tela, No app, Na suíte;
// - digitar não mexe na tela: "Filtrar … por “x”" vira o recorte (o `v-model`), e com a
//   tela filtrada aparece "Tirar o filtro";
// - os resultados são links para o app de destino, com o tipo ao lado;
// - teclado: ↑↓ anda (aria-activedescendant), Esc fecha e MANTÉM o filtro da tela;
// - "/" e Ctrl K abrem de qualquer lugar da tela; a lupa do cabeçalho pede a busca;
// - a variante `hotkey` (Venda do PDV) não põe campo na tela e abre num diálogo.
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

const dialog = () => document.querySelector<HTMLElement>('[role="dialog"]');
const commandInput = () => new DOMWrapper(dialog()!.querySelector("input")!);
const groupLabels = () =>
  [...dialog()!.querySelectorAll("[data-slot='group'] > [data-slot='label']")].map((el) => el.textContent?.trim());

async function openSearch(wrapper: VueWrapper) {
  await wrapper.get("[data-suite-search-input]").trigger("click");
  await nextTick();
  await nextTick();
  return commandInput();
}

describe("OperatorSuiteSearch", () => {
  it("os níveis em ordem fixa: Nesta tela, No app, Na suíte", async () => {
    const wrapper = await mountSearch({ modelValue: "", screenLabel: "filtrando o quadro", "onUpdate:modelValue": () => {} });
    const input = await openSearch(wrapper);
    await input.setValue("maria");
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]![1]).toEqual({ query: { q: "maria" } });
    expect(groupLabels()).toEqual(["Nesta tela", "No app (Gestor)", "Na suíte"]);
    expect(dialog()!.textContent).toContain("Filtrar o quadro por “maria”");

    const results = [...dialog()!.querySelectorAll<HTMLElement>("[data-suite-search-result]")];
    expect(results.map((r) => r.getAttribute("href"))).toEqual([
      "https://gestor.test/X36",
      "https://gestor.test/customers/C1",
      "https://pdv.test/preorders/X36",
    ]);
    expect(results[0]!.getAttribute("aria-label")).toBe("X36 · Maria Santos, Gestor › Pedidos, Em preparo");
    expect(results[0]!.textContent).toContain("Pedidos");
  });

  it("digitar não mexe na tela; Filtrar … por vira o recorte", async () => {
    const wrapper = await mountSearch({ modelValue: "", screenLabel: "filtrando o quadro", "onUpdate:modelValue": () => {} });
    const input = await openSearch(wrapper);
    await input.setValue("maria");
    await settle();
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    dialog()!.querySelector<HTMLElement>("[data-suite-search-screen='apply']")!.click();
    await settle();
    expect(wrapper.emitted("update:modelValue")!.at(-1)).toEqual(["maria"]);
    expect(dialog()).toBeNull();
  });

  it("com a tela filtrada, o painel abre com o termo e oferece tirar o filtro", async () => {
    const wrapper = await mountSearch({ modelValue: "maria", screenLabel: "filtrando o quadro", "onUpdate:modelValue": () => {} });
    expect(wrapper.get("[data-suite-search-input]").text()).toContain("maria");
    const input = await openSearch(wrapper);
    expect((input.element as HTMLInputElement).value).toBe("maria");
    await settle();
    const clear = dialog()!.querySelector<HTMLElement>("[data-suite-search-screen='clear']")!;
    expect(clear.textContent).toContain("Tirar o filtro “maria” do quadro");
    clear.click();
    await settle();
    expect(wrapper.emitted("update:modelValue")!.at(-1)).toEqual([""]);
  });

  it("sem filtro de tela (a Central): só No app e Na suíte", async () => {
    const wrapper = await mountSearch();
    const input = await openSearch(wrapper);
    await input.setValue("maria");
    await settle();
    expect(groupLabels()).toEqual(["No app (Gestor)", "Na suíte"]);
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
    await settle();
    expect(dialog()).toBeNull();
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("termo curto não vai ao servidor e diz o que falta", async () => {
    const wrapper = await mountSearch();
    const input = await openSearch(wrapper);
    await input.setValue("m");
    await settle();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(dialog()!.querySelector("[data-suite-search-hint]")?.textContent).toContain(
      "Digite pelo menos 2 letras para buscar na suíte.",
    );
  });

  it("a suíte fora do ar não apaga o filtro da tela", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    const wrapper = await mountSearch({ modelValue: "", "onUpdate:modelValue": () => {} });
    await (await openSearch(wrapper)).setValue("maria");
    await settle();
    expect(dialog()!.querySelector("[data-suite-search-error]")?.textContent).toContain(
      "O filtro desta tela continua valendo.",
    );
  });

  it("`/` e Ctrl K abrem a busca canônica de qualquer lugar da tela", async () => {
    await mountSearch();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", code: "Slash", bubbles: true, cancelable: true }));
    await settle();
    expect(dialog()).not.toBeNull();
    await commandInput().trigger("keydown", { key: "Escape" });
    await settle();
    expect(dialog()).toBeNull();
    const ctrlK = new KeyboardEvent("keydown", { key: "k", code: "KeyK", ctrlKey: true, bubbles: true, cancelable: true });
    window.dispatchEvent(ctrlK);
    await settle();
    expect(ctrlK.defaultPrevented).toBe(true);
    expect(dialog()).not.toBeNull();
  });

  it("o DashboardSearchButton expõe o atalho com Kbd canônico", async () => {
    const wrapper = await mountSearch();
    expect(wrapper.get("kbd").text()).toBe("/");
  });

  it("a lupa do cabeçalho pede a busca, e a variante `hotkey` abre num diálogo sem campo na tela", async () => {
    const wrapper = await mountSearch({ variant: "hotkey" });
    expect(wrapper.find("[data-suite-search-input]").exists()).toBe(false);
    // `/` é do campo da tela (PDV): não abre a suíte.
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", code: "Slash", bubbles: true, cancelable: true }));
    await settle();
    expect(dialog()).toBeNull();
    useSuiteSearchRequest().request();
    await settle();
    expect(dialog()).not.toBeNull();
    const input = commandInput();
    await input.setValue("maria");
    await settle();
    expect([...dialog()!.querySelectorAll("[data-suite-search-result]")].map((a) => a.getAttribute("href"))).toEqual([
      "https://gestor.test/X36",
      "https://gestor.test/customers/C1",
      "https://pdv.test/preorders/X36",
    ]);
    await input.trigger("keydown", { key: "Escape" });
    await settle();
    expect(dialog()).toBeNull();
  });
});
