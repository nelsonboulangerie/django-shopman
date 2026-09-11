import { defineComponent, h, mergeProps } from "vue";

// Os testes montam os formulários sem o runtime Nuxt. Este stub conserva o
// elemento nativo e o contrato de v-model do UiNativeSelect compartilhado.
export const UiNativeSelectStub = defineComponent({
  name: "UiNativeSelectStub",
  inheritAttrs: false,
  props: { modelValue: { default: undefined } },
  emits: ["update:modelValue", "change"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        "select",
        mergeProps(attrs, {
          value: props.modelValue,
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
