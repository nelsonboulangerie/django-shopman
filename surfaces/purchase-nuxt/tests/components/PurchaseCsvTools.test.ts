import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import PurchaseCsvTools from "../../app/components/PurchaseCsvTools.vue";
const Import = defineComponent({
  props: ["open", "preview", "error", "busy"],
  emits: ["preview", "apply"],
  setup(props, { emit }) {
    return () =>
      h("div", [
        h("span", String(props.open)),
        h("p", props.error),
        h(
          "button",
          { onClick: () => emit("preview", "SKU;Nome;Unidade\nA;A;kg") },
          "Prévia",
        ),
        h(
          "button",
          { onClick: () => emit("apply", props.preview?.base_revision) },
          "Aplicar",
        ),
      ]);
  },
});
const Modal = defineComponent({
  props: ["open"],
  setup(props, { slots }) {
    return () => (props.open ? h("div", slots.body?.()) : null);
  },
});
const Export = defineComponent({
  props: ["table", "fileName"],
  setup(props) {
    return () => h("button", JSON.stringify(props.table));
  },
});
function tools() {
  return mount(PurchaseCsvTools, {
    props: { entity: "materials" },
    global: {
      stubs: {
        OperatorCsvImport: Import,
        NuxtModal: Modal,
        OperatorCsvExportButton: Export,
      },
    },
  });
}
function preview(errors: unknown[] = []) {
  return {
    rows: 1,
    totals: { new: 1 },
    changes: [{ ref: "A", name: "A", action: "Criar" }],
    errors,
    base_revision: "revision",
  };
}
describe("CSV da Base", () => {
  it("mostra prévia antes de aplicar e mantém intenção ao repetir após resposta perdida", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ preview: preview() })
      .mockRejectedValueOnce(new Error("timeout"))
      .mockResolvedValueOnce({ ok: true, outcome: "applied" });
    vi.stubGlobal("$fetch", fetch);
    const wrapper = tools();
    (wrapper.vm as unknown as { openImport(): void }).openImport();
    await wrapper.findAll("button")[0]!.trigger("click");
    await flushPromises();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]![1].body.preview).toBe(true);
    await wrapper.findAll("button")[1]!.trigger("click");
    await flushPromises();
    expect(wrapper.emitted("applied")).toBeUndefined();
    await wrapper.findAll("button")[1]!.trigger("click");
    await flushPromises();
    expect(fetch.mock.calls[1]![1].headers["Idempotency-Key"]).toBe(
      fetch.mock.calls[2]![1].headers["Idempotency-Key"],
    );
    expect(wrapper.emitted("applied")).toHaveLength(1);
  });
  it("resultado em processamento mantém a intenção e não anuncia aplicação", async () => {
    const fetch = vi.fn().mockResolvedValueOnce({ preview: preview() }).mockResolvedValueOnce({ outcome: "unknown" }).mockResolvedValueOnce({ ok: true, outcome: "applied" });
    vi.stubGlobal("$fetch", fetch);
    const wrapper = tools();
    await wrapper.findAll("button")[0]!.trigger("click"); await flushPromises();
    await wrapper.findAll("button")[1]!.trigger("click"); await flushPromises();
    expect(wrapper.emitted("applied")).toBeUndefined();
    expect(wrapper.text()).toContain("ainda não foi confirmada");
    await wrapper.findAll("button")[1]!.trigger("click"); await flushPromises();
    expect(fetch.mock.calls[1]![1].headers["Idempotency-Key"]).toBe(fetch.mock.calls[2]![1].headers["Idempotency-Key"]);
    expect(wrapper.emitted("applied")).toHaveLength(1);
  });
  it("erro por registro impede aplicação", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({
        preview: preview([{ row: 2, detail: "Unidade inválida" }]),
      });
    vi.stubGlobal("$fetch", fetch);
    const wrapper = tools();
    await wrapper.findAll("button")[0]!.trigger("click");
    await flushPromises();
    await wrapper.findAll("button")[1]!.trigger("click");
    await flushPromises();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("exporta todos os registros pelo botão do kit", async () => {
    vi.stubGlobal(
      "$fetch",
      vi
        .fn()
        .mockResolvedValue({
          table: { header: ["SKU"], rows: [["A"], ["B"]] },
        }),
    );
    const wrapper = tools();
    await (
      wrapper.vm as unknown as { openExport(): Promise<void> }
    ).openExport();
    await flushPromises();
    expect(wrapper.text()).toContain("2 insumos no arquivo.");
    expect(wrapper.findComponent(Export).props("table").rows).toHaveLength(2);
  });
});
