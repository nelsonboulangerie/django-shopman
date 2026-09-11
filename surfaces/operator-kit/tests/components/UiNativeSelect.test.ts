import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { h, type VueWrapper } from "vue";

import UiNativeSelect from "../../app/components/UiNativeSelect.vue";

const mounted: VueWrapper[] = [];

async function mountSelect(options: Parameters<typeof mountSuspended>[1] = {}) {
  const wrapper = await mountSuspended(UiNativeSelect, options);
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("UiNativeSelect", () => {
  it("renderiza um select nativo autocontido e encaminha atributos", async () => {
    const wrapper = await mountSelect({
      props: { modelValue: "second", class: "w-auto" },
      attrs: {
        name: "recipe-kind",
        disabled: true,
        "aria-label": "Tipo de receita",
      },
      slots: {
        default: () => [
          h("option", { value: "first" }, "Primeiro"),
          h("option", { value: "second" }, "Segundo"),
        ],
      },
    });

    const select = wrapper.get("select");
    expect(select.attributes()).toMatchObject({
      name: "recipe-kind",
      disabled: "",
      "aria-label": "Tipo de receita",
      "data-slot": "native-select",
    });
    expect((select.element as HTMLSelectElement).value).toBe("second");
    expect(select.classes()).toEqual(
      expect.arrayContaining([
        "h-11",
        "rounded-md",
        "bg-background",
        "focus-visible:ring-[3px]",
        "focus-visible:ring-ring/50",
        "w-auto",
      ]),
    );
    expect(select.classes()).not.toContain("w-full");
  });

  it("implementa v-model e repassa o mesmo evento change nativo", async () => {
    const wrapper = await mountSelect({
      props: { modelValue: "first" },
      slots: {
        default: () => [
          h("option", { value: "first" }, "Primeiro"),
          h("option", { value: "second" }, "Segundo"),
        ],
      },
    });

    await wrapper.get("select").setValue("second");

    expect(wrapper.emitted("update:modelValue")).toEqual([["second"]]);
    const change = wrapper.emitted("change")?.[0]?.[0];
    expect(change).toBeInstanceOf(Event);
    expect((change?.target as HTMLSelectElement).value).toBe("second");
  });

  it("preserva valores tipados das options e o contrato sem v-model", async () => {
    const controlled = await mountSelect({
      props: { modelValue: 1 },
      slots: {
        default: () => [
          h("option", { value: 1 }, "Um"),
          h("option", { value: 2 }, "Dois"),
        ],
      },
    });
    await controlled.get("select").setValue("2");
    expect(controlled.emitted("update:modelValue")).toEqual([[2]]);

    const uncontrolled = await mountSelect({
      attrs: { value: "b" },
      slots: {
        default: () => [
          h("option", { value: "a" }, "A"),
          h("option", { value: "b" }, "B"),
        ],
      },
    });
    expect(
      (uncontrolled.get("select").element as HTMLSelectElement).value,
    ).toBe("b");
  });
});
