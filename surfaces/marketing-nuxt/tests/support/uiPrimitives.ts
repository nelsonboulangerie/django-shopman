import { config } from "@vue/test-utils";
import { defineComponent, h } from "vue";

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
  UiInput,
  UiTextarea,
};
