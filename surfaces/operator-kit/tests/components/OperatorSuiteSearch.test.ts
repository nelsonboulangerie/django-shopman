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

describe("OperatorSuiteSearch", () => {
  it("digitar filtra a tela e abre o painel com o alcance e a suíte por tipo", async () => {
    const wrapper = await mountSearch({ modelValue: "", screenLabel: "filtrando o quadro", "onUpdate:modelValue": () => {} });
    const input = wrapper.get("[data-suite-search-input]");
    expect(input.attributes("role")).toBe("combobox");
    await input.setValue("maria");
    expect(wrapper.emitted("update:modelValue")!.at(-1)).toEqual(["maria"]);
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]![1]).toEqual({ query: { q: "maria" } });

    const panel = wrapper.get("[data-suite-search-panel]");
    const scopes = panel.findAll("[data-suite-search-scope]");
    expect(scopes.map((s) => s.text())).toEqual(["Esta tela", "Gestor 2", "Toda a suíte 3"]);
    expect(panel.text()).toContain("Nesta tela · filtrando o quadro");
    expect(panel.findAll("[data-suite-search-group]").map((g) => g.text())).toEqual(["Pedidos", "Clientes", "Encomendas"]);
    const results = panel.findAll("[data-suite-search-result]");
    expect(results.map((r) => r.attributes("href"))).toEqual([
      "https://gestor.test/X36",
      "https://gestor.test/customers/C1",
      "https://pdv.test/preorders/X36",
    ]);
    expect(results[0]!.attributes("role")).toBe("option");
    expect(results[0]!.attributes("aria-label")).toBe("X36 · Maria Santos, Gestor › Pedidos, Em preparo");
    expect(results[0]!.find("mark").text()).toBe("Maria");
  });

  it("Tab troca o alcance: o App recorta pelo app atual", async () => {
    const wrapper = await mountSearch();
    const input = wrapper.get("[data-suite-search-input]");
    await input.setValue("maria");
    await settle();
    // Sem v-model, a tela não filtra: o primeiro alcance é o App.
    const panel = () => wrapper.get("[data-suite-search-panel]");
    expect(panel().findAll("[data-suite-search-scope]").map((s) => s.attributes("data-suite-search-scope"))).toEqual(["app", "suite"]);
    expect(panel().findAll("[data-suite-search-result]")).toHaveLength(2);
    await input.trigger("keydown", { key: "Tab" });
    expect(panel().get("[data-suite-search-scope='suite']").attributes("aria-checked")).toBe("true");
    expect(panel().findAll("[data-suite-search-result]")).toHaveLength(3);
  });

  it("↑↓ anda pelos resultados (aria-activedescendant) e Esc fecha mantendo o filtro", async () => {
    const wrapper = await mountSearch({ modelValue: "", "onUpdate:modelValue": () => {} });
    const input = wrapper.get("[data-suite-search-input]");
    await input.setValue("maria");
    await settle();
    await input.trigger("keydown", { key: "ArrowDown" });
    const activeId = input.attributes("aria-activedescendant");
    expect(activeId).toBeTruthy();
    expect(wrapper.get(`#${activeId}`).attributes("aria-selected")).toBe("true");
    await input.trigger("keydown", { key: "ArrowUp" });
    expect(input.attributes("aria-activedescendant")).not.toBe(activeId);
    await input.trigger("keydown", { key: "Escape" });
    expect(wrapper.find("[data-suite-search-panel]").exists()).toBe(false);
    expect((input.element as HTMLInputElement).value).toBe("maria");
    expect(wrapper.emitted("update:modelValue")!.some((e) => e[0] === "")).toBe(false);
  });

  it("termo curto não vai ao servidor e diz o que falta", async () => {
    const wrapper = await mountSearch();
    const input = wrapper.get("[data-suite-search-input]");
    await input.setValue("m");
    await settle();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(wrapper.get("[data-suite-search-hint]").text()).toBe("Digite pelo menos 2 letras para buscar na suíte.");
  });

  it("a suíte fora do ar não apaga o filtro da tela", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    const wrapper = await mountSearch({ modelValue: "", "onUpdate:modelValue": () => {} });
    await wrapper.get("[data-suite-search-input]").setValue("maria");
    await settle();
    expect(wrapper.get("[data-suite-search-error]").text()).toContain("O filtro desta tela continua valendo.");
  });

  it("`/` e Ctrl K levam ao campo de qualquer lugar da tela", async () => {
    const wrapper = await mountSearch();
    const input = wrapper.get("[data-suite-search-input]").element as HTMLInputElement;
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true }));
    await nextTick();
    expect(document.activeElement).toBe(input);
    input.blur();
    const ctrlK = new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true, cancelable: true });
    window.dispatchEvent(ctrlK);
    await nextTick();
    expect(ctrlK.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(input);
  });

  it("a tecla não é impressa no toque (só com ponteiro fino)", async () => {
    const wrapper = await mountSearch();
    expect(wrapper.get("[data-search-shortcut]").classes()).toEqual(expect.arrayContaining(["hidden", "pointer-fine:flex"]));
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
    const dialog = document.querySelector("[data-suite-search-dialog]")!;
    expect(dialog.getAttribute("role")).toBe("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const input = dialog.querySelector<HTMLInputElement>("[data-suite-search-dialog-input]")!;
    input.value = "maria";
    input.dispatchEvent(new Event("input"));
    await settle();
    expect([...dialog.querySelectorAll("[data-suite-search-result]")].map((a) => a.getAttribute("href"))).toEqual(["https://gestor.test/X36", "https://gestor.test/customers/C1"]);
    // Os chips: o alcance (o App primeiro, sem filtro de tela) e, depois, os tipos dele.
    expect([...dialog.querySelectorAll("[data-suite-search-scope]")].map((c) => c.getAttribute("data-suite-search-scope"))).toEqual(["app", "suite"]);
    expect([...dialog.querySelectorAll("[data-suite-search-type]")].map((c) => c.getAttribute("data-suite-search-type"))).toEqual(["orders", "customers"]);
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await nextTick();
    expect(document.querySelector("[data-suite-search-dialog]")).toBeNull();
  });
});
