import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PurchaseSupplierBulkBar from "../../app/components/PurchaseSupplierBulkBar.vue";
const Bar = defineComponent({
  props: ["items", "count", "placement"],
  emits: ["clear"],
  setup(props, { slots, emit }) {
    return () =>
      h("div", [
        h("span", String(props.count)),
        ...props.items
          .flat()
          .map(
            (item: {
              label: string;
              disabled: boolean;
              onSelect: () => void;
            }) =>
              h(
                "button",
                { disabled: item.disabled, onClick: item.onSelect },
                item.label,
              ),
          ),
        h("button", { onClick: () => emit("clear") }, "Limpar"),
        slots.lead?.(),
      ]);
  },
});
const Timed = defineComponent({
  props: ["until", "serverNow", "label"],
  emits: ["click"],
  setup(props, { emit }) {
    return () => h("button", { onClick: () => emit("click") }, props.label);
  },
});
function mountBar(pending = false) {
  return mount(PurchaseSupplierBulkBar, {
    props: {
      count: 3,
      pending,
      undo: {
        until: "2026-10-20T20:00:15Z",
        serverNow: "2026-10-20T20:00:00Z",
      },
    },
    global: { stubs: { OperatorBulkBar: Bar, OperatorTimedButton: Timed } },
  });
}
describe("lote de fornecedores", () => {
  it("arquiva e desarquiva e oferece Desfazer com prazo", async () => {
    const wrapper = mountBar();
    const buttons = wrapper.findAll("button");
    await buttons[0]!.trigger("click");
    await buttons[1]!.trigger("click");
    expect(wrapper.emitted("archive")).toEqual([[false], [true]]);
    await buttons[3]!.trigger("click");
    expect(wrapper.emitted("undo")).toHaveLength(1);
    expect(wrapper.findComponent(Timed).props("until")).toBe(
      "2026-10-20T20:00:15Z",
    );
    await buttons[2]!.trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });
  it("bloqueia novas ações enquanto aguarda o lote", () => {
    const wrapper = mountBar(true);
    expect(
      wrapper
        .findAll("button")
        .slice(0, 2)
        .every((button) => button.attributes("disabled") !== undefined),
    ).toBe(true);
  });
});
