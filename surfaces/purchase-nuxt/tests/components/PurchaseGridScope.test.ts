import { mount } from "@vue/test-utils";
import { computed, defineComponent, h, ref } from "vue";
import { describe, expect, it } from "vitest";
import { usePurchaseGridFields } from "../../app/composables/usePurchaseGridFields";

for (const kind of ["cost", "minimum"] as const) {
  describe(`rascunhos filtrados de ${kind}`, () => {
    it("o erro oculto não bloqueia o lote visível e salvar preserva seu rascunho e desfazer", async () => {
      const wrapper = mount(
        defineComponent({
          setup() {
            const inputs = ref<Record<string, string>>({});
            const grid = usePurchaseGridFields(inputs, kind);
            grid.set("hidden", "inválido");
            grid.set("visible", "2,50");
            const visible = ref([{ sku: "visible" }]);
            const errors = computed(() => grid.errorsFor(visible.value));
            return () =>
              h("section", [
                h("output", JSON.stringify(inputs.value)),
                h("p", JSON.stringify(errors.value)),
                h(
                  "button",
                  {
                    disabled: !!Object.keys(errors.value).length,
                    onClick: () => grid.clear(["visible"]),
                  },
                  "Salvar",
                ),
                h(
                  "button",
                  {
                    onClick: () => {
                      visible.value = [{ sku: "hidden" }];
                    },
                  },
                  "Mostrar oculto",
                ),
                h("button", { onClick: grid.undo }, "Desfazer"),
              ]);
          },
        }),
      );
      expect(wrapper.get("button").attributes("disabled")).toBeUndefined();
      await wrapper.get("button").trigger("click");
      expect(wrapper.get("output").text()).toBe('{"hidden":"inválido"}');
      await wrapper.findAll("button")[1]!.trigger("click");
      expect(wrapper.get("p").text()).toContain('"hidden":');
      await wrapper.findAll("button")[2]!.trigger("click");
      expect(wrapper.get("output").text()).toBe("{}");
    });
  });
}
