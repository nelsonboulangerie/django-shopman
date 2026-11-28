import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { describe, expect, it } from "vitest";
import { usePurchaseGridFields } from "../../app/composables/usePurchaseGridFields";

function editor(kind: "cost" | "minimum" = "cost") {
  return mount(
    defineComponent({
      setup() {
        const inputs = ref<Record<string, string>>({});
        const grid = usePurchaseGridFields(inputs, kind);
        return () =>
          h("section", [
            ...["A", "B", "C"].map((sku) =>
              h("input", {
                "data-sku": sku,
                value: inputs.value[sku] || "",
                onInput: (event: Event) =>
                  grid.set(sku, (event.target as HTMLInputElement).value),
                onPaste: (event: ClipboardEvent) =>
                  grid.paste(event, sku, [
                    { sku: "A" },
                    { sku: "B" },
                    { sku: "C" },
                  ]),
              }),
            ),
            h(
              "button",
              { disabled: !grid.canUndo.value, onClick: grid.undo },
              "Desfazer",
            ),
            h("output", JSON.stringify(grid.errors.value)),
          ]);
      },
    }),
  );
}
function paste(text: string) {
  return { clipboardData: { getData: () => text }, preventDefault() {} };
}
describe("Tabelão de insumos", () => {
  it("cola TSV na ordem visível a partir do foco e desfaz uma edição por vez", async () => {
    const wrapper = editor();
    await wrapper
      .get('[data-sku="B"]')
      .trigger("paste", paste("12,50\tignorado\n20,75\tignorado"));
    expect(
      (wrapper.get('[data-sku="A"]').element as HTMLInputElement).value,
    ).toBe("");
    expect(
      (wrapper.get('[data-sku="B"]').element as HTMLInputElement).value,
    ).toBe("12,50");
    expect(
      (wrapper.get('[data-sku="C"]').element as HTMLInputElement).value,
    ).toBe("20,75");
    await wrapper.get("button").trigger("click");
    expect(
      (wrapper.get('[data-sku="C"]').element as HTMLInputElement).value,
    ).toBe("");
    expect(
      (wrapper.get('[data-sku="B"]').element as HTMLInputElement).value,
    ).toBe("12,50");
  });
  it("preserva vírgula decimal de uma coluna e acusa erro por insumo antes de salvar", async () => {
    const wrapper = editor();
    await wrapper.get("input").trigger("paste", paste('"12,50"\ninválido\n0'));
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe(
      "12,50",
    );
    expect(wrapper.get("output").text()).toContain('"B":');
    expect(wrapper.get("output").text()).toContain('"C":');
    expect(wrapper.get("output").text()).not.toContain('"A":');
  });
  it("aceita zero para retirar o mínimo e desfaz digitação sobre valor colado", async () => {
    const wrapper = editor("minimum");
    await wrapper.get("input").trigger("paste", paste("0;\n2,5;\n3.5;"));
    expect(wrapper.get("output").text()).toBe("{}");
    await wrapper.get("input").setValue("9");
    await wrapper.get("button").trigger("click");
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("0");
  });
});
