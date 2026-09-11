import { defineComponent, h, mergeProps, ref } from "vue";

// Os testes de componente da Produção rodam sem o runtime Nuxt. Estes stubs
// preservam a semântica nativa dos primitivos: continuam sendo elementos reais,
// encaminham attrs/listeners e mantêm o contrato de v-model usado pelas telas.
export const UiButtonStub = defineComponent({
  name: "UiButtonStub",
  inheritAttrs: false,
  setup(_props, { attrs, slots }) {
    return () => h("button", attrs, slots.default?.());
  },
});

export const UiInputStub = defineComponent({
  name: "UiInputStub",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "" },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, expose }) {
    const inputRef = ref<HTMLInputElement | null>(null);
    expose({ inputRef });

    return () =>
      h(
        "input",
        mergeProps(attrs, {
          ref: inputRef,
          value: props.modelValue,
          onInput: (event: Event) =>
            emit("update:modelValue", (event.target as HTMLInputElement).value),
        }),
      );
  },
});

export const UiTextareaStub = defineComponent({
  name: "UiTextareaStub",
  inheritAttrs: false,
  props: {
    modelValue: { type: String, default: "" },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h(
        "textarea",
        mergeProps(attrs, {
          value: props.modelValue,
          onInput: (event: Event) =>
            emit(
              "update:modelValue",
              (event.target as HTMLTextAreaElement).value,
            ),
        }),
      );
  },
});

export const UiNativeSelectStub = defineComponent({
  name: "UiNativeSelectStub",
  inheritAttrs: false,
  props: {
    modelValue: { default: undefined },
  },
  emits: ["update:modelValue", "change"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        "select",
        mergeProps(attrs, {
          ...(props.modelValue === undefined
            ? {}
            : { value: props.modelValue }),
          onChange: (event: Event) => {
            emit(
              "update:modelValue",
              (event.target as HTMLSelectElement).value,
            );
            emit("change", event);
          },
        }),
        slots.default?.(),
      );
  },
});
