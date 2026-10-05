import { config } from "@vue/test-utils";
import { Fragment, defineComponent, h, inject, provide } from "vue";

// O interruptor entra de VERDADE, não como stub: ele vive no operator-kit e é SFC
// puro (nenhum runtime Nuxt). Stubar seria justamente apagar o contrato que estes
// testes cobram — `role="switch"` e `aria-checked` —, e foi um trilho escrito à mão
// nesta mesma tela que motivou a promoção. Mesmo arranjo do Marketing
// (`marketing-nuxt/tests/support/uiPrimitives.ts`).
import UiSwitch from "../../../operator-kit/app/components/UiSwitch.vue";
import UiCheckbox from "../../../operator-kit/app/components/UiCheckbox.vue";
import UiCheckboxGroup from "../../../operator-kit/app/components/UiCheckboxGroup.vue";
// O detalhe do pedido também entra de verdade: é o kit que desenha as seções do
// `pages/[ref].vue` (a mesma tela do detalhe da encomenda no PDV), e stubá-lo
// apagaria justamente o que os testes da página cobram.
import OperatorOrderDetail from "../../../operator-kit/app/components/OperatorOrderDetail.vue";
// O grupo de rádio da vocação (painel do produto) entra de verdade pelo mesmo
// motivo: o contrato cobrado é `role="radio"`/`aria-checked` do kit.
import UiRadio from "../../../operator-kit/app/components/UiRadio.vue";
import UiRadioGroup from "../../../operator-kit/app/components/UiRadioGroup.vue";
import UiTabs from "../../../operator-kit/app/components/Ui/Tabs/Tabs.vue";
import UiTabsList from "../../../operator-kit/app/components/Ui/Tabs/List.vue";
import UiTabsTrigger from "../../../operator-kit/app/components/Ui/Tabs/Trigger.vue";

const popoverToggleKey = Symbol("popover-toggle");
const UiPopover = defineComponent({
  name: "UiPopover",
  props: { open: Boolean },
  emits: ["update:open"],
  setup(props, { emit, slots }) {
    provide(popoverToggleKey, () => emit("update:open", !props.open));
    return () => h(Fragment, slots.default?.());
  },
});
const UiPopoverTrigger = defineComponent({
  name: "UiPopoverTrigger",
  setup(_, { slots }) {
    const toggle = inject<() => void>(popoverToggleKey, () => undefined);
    return () => h("span", { onClick: toggle }, slots.default?.());
  },
});
const passthrough = (name: string) => defineComponent({
  name,
  setup(_, { slots }) {
    return () => h(Fragment, slots.default?.());
  },
});
const passthroughRoot = (name: string) => defineComponent({
  name,
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("div", attrs, slots.default?.());
  },
});

const NuxtCheckbox = defineComponent({
  name: "NuxtCheckbox",
  inheritAttrs: false,
  props: {
    modelValue: { type: [Boolean, String], default: false },
    disabled: Boolean,
    label: String,
    description: String,
    ui: { type: Object as () => Record<string, string>, default: () => ({}) },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, slots }) {
    return () => {
      const checked = props.modelValue === true;
      const mixed = props.modelValue === "indeterminate";
      return h("div", {
        "data-slot": attrs["data-slot"] ?? "checkbox",
        class: ["relative flex", props.ui.root],
      }, [
        h("div", { "data-slot": "container" }, h("button", {
          ...attrs,
          "data-slot": "base",
          role: "checkbox",
          type: "button",
          disabled: props.disabled,
          "aria-label": attrs["aria-label"] ?? props.label,
          "aria-checked": mixed ? "mixed" : String(checked),
          "data-state": mixed ? "indeterminate" : checked ? "checked" : "unchecked",
          class: props.ui.base,
          onClick: () => emit("update:modelValue", mixed || !checked),
        })),
        h("div", { "data-slot": "wrapper", class: props.ui.wrapper }, [
          h("label", slots.label?.() ?? props.label),
          slots.description?.() ?? (props.description ? h("span", props.description) : null),
        ]),
      ]);
    };
  },
});

const NuxtCheckboxGroup = defineComponent({
  name: "NuxtCheckboxGroup",
  inheritAttrs: false,
  props: {
    modelValue: { type: Array as () => unknown[], default: () => [] },
    items: { type: Array as () => Array<Record<string, unknown>>, default: () => [] },
    legend: String,
    disabled: Boolean,
    valueKey: { type: String, default: "value" },
    labelKey: { type: String, default: "label" },
    descriptionKey: { type: String, default: "description" },
    ui: { type: Object as () => Record<string, string>, default: () => ({}) },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, slots }) {
    const toggle = (item: Record<string, unknown>) => {
      if (props.disabled || item.disabled) return;
      const value = item[props.valueKey];
      const next = props.modelValue.includes(value)
        ? props.modelValue.filter((current) => current !== value)
        : [...props.modelValue, value];
      emit("update:modelValue", next);
    };
    return () => h("div", { ...attrs, "data-slot": attrs["data-slot"] ?? "checkbox-group", class: props.ui.root }, [
      h("fieldset", { "data-slot": "fieldset", class: props.ui.fieldset }, [
        props.legend || slots.legend
          ? h("legend", { "data-slot": "legend", class: props.ui.legend }, slots.legend?.() ?? props.legend)
          : null,
        ...props.items.map((item) => {
          const value = item[props.valueKey];
          const checked = props.modelValue.includes(value);
          const dataAttrs = Object.fromEntries(Object.entries(item).filter(([key]) => key.startsWith("data-")));
          return h("div", { ...dataAttrs, "data-slot": "item", class: props.ui.item }, [
            h("button", {
              type: "button",
              role: "checkbox",
              disabled: props.disabled || Boolean(item.disabled),
              "aria-checked": String(checked),
              class: props.ui.base,
              onClick: () => toggle(item),
            }),
            h("span", { "data-slot": "wrapper" }, [
              h("span", { "data-slot": "label" }, slots.label?.({ item }) ?? String(item[props.labelKey] ?? "")),
              item[props.descriptionKey]
                ? h("span", { "data-slot": "description" }, slots.description?.({ item }) ?? String(item[props.descriptionKey]))
                : null,
            ]),
          ]);
        }),
      ]),
    ]);
  },
});

const NuxtSwitch = defineComponent({
  name: "NuxtSwitch",
  inheritAttrs: false,
  props: {
    modelValue: Boolean,
    disabled: Boolean,
    ui: { type: Object as () => Record<string, string>, default: () => ({}) },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () => h("div", { "data-slot": attrs["data-slot"] ?? "switch", class: props.ui.root }, [
      h("button", {
        ...attrs,
        type: "button",
        role: "switch",
        disabled: props.disabled,
        "aria-checked": String(props.modelValue),
        "data-state": props.modelValue ? "checked" : "unchecked",
        class: props.ui.base,
        onClick: () => emit("update:modelValue", !props.modelValue),
      }),
    ]);
  },
});

config.global.components = {
  ...config.global.components,
  UiSwitch,
  UiCheckbox,
  UiCheckboxGroup,
  NuxtCheckbox,
  NuxtCheckboxGroup,
  NuxtSwitch,
  OperatorOrderDetail,
  UiRadio,
  UiRadioGroup,
  UiTabs,
  UiTabsList,
  UiTabsTrigger,
  UiPopover,
  UiPopoverTrigger,
  UiPopoverContent: passthroughRoot("UiPopoverContent"),
  UiSheet: passthrough("UiSheet"),
  UiSheetContent: passthroughRoot("UiSheetContent"),
};
