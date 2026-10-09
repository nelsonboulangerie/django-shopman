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

// A tabela da suíte (`OperatorTable`, kit) sem o Nuxt UI: uma `<table>` com o cabeçalho
// das colunas e cada célula pelo slot `#<id>-cell` (o mesmo contrato da `NuxtTable`) ou
// pelo `accessorKey`. O vazio mostra o `empty-title`; o `#expanded` aparece para a linha
// marcada em `expanded`.
type StubColumn = { id?: string; accessorKey?: string; header?: string };
export const OperatorTableStub = defineComponent({
  name: "OperatorTableStub",
  inheritAttrs: false,
  props: {
    data: { type: Array, default: () => [] },
    columns: { type: Array, default: () => [] },
    rowKey: { type: Function, required: true },
    emptyTitle: { type: String, default: "" },
    caption: { type: String, default: "" },
    expanded: { type: Object, default: () => ({}) },
  },
  setup(props, { attrs, slots }) {
    return () => {
      const columns = props.columns as StubColumn[];
      const rows = props.data as Record<string, unknown>[];
      if (!rows.length) return h("div", { ...attrs, "data-operator-table-empty": "" }, props.emptyTitle);
      return h("table", attrs, [
        h("caption", props.caption),
        h("thead", h("tr", columns.map((column) => h("th", column.header ?? "")))),
        h(
          "tbody",
          rows.flatMap((original) => {
            const key = String((props.rowKey as (row: unknown) => string)(original));
            const row = { original, id: key };
            const cells = columns.map((column) => {
              const id = column.id ?? column.accessorKey ?? "";
              const slot = slots[`${id}-cell`];
              return h("td", slot ? slot({ row }) : String(original[column.accessorKey ?? ""] ?? ""));
            });
            const out = [h("tr", { "data-row": key }, cells)];
            if (slots.expanded && (props.expanded as Record<string, boolean>)[key])
              out.push(h("tr", h("td", { colspan: columns.length }, slots.expanded({ row }))));
            return out;
          }),
        ),
        slots.footer ? h("tfoot", h("tr", h("td", slots.footer()))) : null,
      ]);
    };
  },
});
