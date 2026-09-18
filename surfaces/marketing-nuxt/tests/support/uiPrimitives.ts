import { config } from "@vue/test-utils";
import { defineComponent, h } from "vue";

// Os primitivos de ESCOLHA entram de verdade, não como stub: eles vivem no
// operator-kit e são SFC puro (nenhum runtime Nuxt, só o `Icon`, que cada teste já
// stuba). Stub de checkbox/rádio/select seria justamente o lugar onde o contrato
// que interessa — `aria-checked`, `mixed`, teclado — deixaria de ser testado aqui.
import UiCheckbox from "../../../operator-kit/app/components/UiCheckbox.vue";
import UiRadio from "../../../operator-kit/app/components/UiRadio.vue";
import UiRadioGroup from "../../../operator-kit/app/components/UiRadioGroup.vue";
import UiSelect from "../../../operator-kit/app/components/UiSelect.vue";

function invoke(listener: unknown, event: Event) {
  if (Array.isArray(listener)) {
    for (const candidate of listener) invoke(candidate, event);
    return;
  }
  if (typeof listener === "function") listener(event);
}

const UiButton = defineComponent({
  name: "UiButton",
  inheritAttrs: false,
  props: {
    disabled: Boolean,
    type: { type: String, default: "button" },
    variant: { type: String, default: "default" },
  },
  setup(props, { attrs, slots }) {
    return () =>
      h(
        "button",
        {
          ...attrs,
          class: [
            props.variant === "outline" ? "border" : "bg-primary",
            attrs.class,
          ],
          disabled: props.disabled,
          type: props.type,
        },
        slots.default?.(),
      );
  },
});

const UiInput = defineComponent({
  name: "UiInput",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "" },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h("input", {
        ...attrs,
        value: props.modelValue,
        onInput: (event: Event) => {
          emit("update:modelValue", (event.target as HTMLInputElement).value);
          invoke(attrs.onInput, event);
        },
      });
  },
});

const UiTextarea = defineComponent({
  name: "UiTextarea",
  inheritAttrs: false,
  props: {
    modelValue: { type: String, default: "" },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h("textarea", {
        ...attrs,
        value: props.modelValue,
        onInput: (event: Event) => {
          emit(
            "update:modelValue",
            (event.target as HTMLTextAreaElement).value,
          );
          invoke(attrs.onInput, event);
        },
      });
  },
});

config.global.components = {
  ...config.global.components,
  UiButton,
  UiCheckbox,
  UiInput,
  UiRadio,
  UiRadioGroup,
  UiSelect,
  UiTextarea,
};
