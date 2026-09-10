import { describe, expect, it, vi } from "vitest";
import { ref, watch, onBeforeUnmount, nextTick } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import CatalogAiSuggest from "../../app/components/CatalogAiSuggest.vue";
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);

it("não exibe resposta de A no mesmo campo do SKU B", async () => {
  let resolve!: (s: string) => void;
  const assist = vi.fn(() => new Promise<string>((r) => { resolve = r; }));
  const w = mount(CatalogAiSuggest, { props: { sku: "A", field: "description", label: "Descrição", current: "", busy: false, assist }, global: { stubs: { Icon: true } } });
  await w.find("button").trigger("click");
  await w.setProps({ sku: "B" });
  resolve("Texto confidencial do SKU A");
  await flushPromises();
  expect(w.text()).not.toContain("Texto confidencial");
  expect(w.findAll("button").some(b => b.text() === "Aceitar")).toBe(false);
});

describe("base da sugestão", () => {
  it("digitação depois do pedido invalida a resposta antiga", async () => {
    let resolve!: (s: string) => void;
    const assist = () => new Promise<string>((r) => { resolve = r; });
    const w = mount(CatalogAiSuggest, { props: { sku: "A", field: "description", label: "Descrição", current: "Original", busy: false, assist }, global: { stubs: { Icon: true } } });
    await w.find("button").trigger("click");
    await w.setProps({ current: "Meu rascunho novo" });
    resolve("Sugestão para base antiga");
    await flushPromises();
    expect(w.text()).not.toContain("Sugestão para base antiga");
    await nextTick();
  });
});
