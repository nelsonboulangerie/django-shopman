import { config } from "@vue/test-utils";
import { Fragment, defineComponent, h, inject, provide, ref } from "vue";

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
// O ⋯ único entra de verdade: o contrato (o nome do botão, os grupos, o motivo de uma
// ação que não pode) é do kit, e o menu por baixo é o `NuxtDropdownMenu` deste harness.
import OperatorMoreMenu from "../../../operator-kit/app/components/OperatorMoreMenu.vue";
// O botão com prazo entra de verdade: o Desfazer da saída (cartão e detalhe) é ele, e o
// contrato cobrado (rótulo fixo, prazo absoluto, some no fim) é do kit.
import OperatorTimedButton from "../../../operator-kit/app/components/OperatorTimedButton.vue";
import UiTabs from "../../../operator-kit/app/components/Ui/Tabs/Tabs.vue";
import UiTabsList from "../../../operator-kit/app/components/Ui/Tabs/List.vue";
import UiTabsTrigger from "../../../operator-kit/app/components/Ui/Tabs/Trigger.vue";

const popoverToggleKey = Symbol("popover-toggle");
const formFieldLabelKey = Symbol("form-field-label");
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
const passthrough = (name: string) =>
  defineComponent({
    name,
    setup(_, { slots }) {
      return () => h(Fragment, slots.default?.());
    },
  });
const passthroughRoot = (name: string) =>
  defineComponent({
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
      return h(
        "div",
        {
          "data-slot": attrs["data-slot"] ?? "checkbox",
          class: ["relative flex", props.ui.root],
        },
        [
          h(
            "div",
            { "data-slot": "container" },
            h("button", {
              ...attrs,
              "data-slot": "base",
              role: "checkbox",
              type: "button",
              disabled: props.disabled,
              "aria-label": attrs["aria-label"] ?? props.label,
              "aria-checked": mixed ? "mixed" : String(checked),
              "data-state": mixed
                ? "indeterminate"
                : checked
                  ? "checked"
                  : "unchecked",
              class: props.ui.base,
              onClick: () => emit("update:modelValue", mixed || !checked),
            }),
          ),
          h("div", { "data-slot": "wrapper", class: props.ui.wrapper }, [
            h("label", slots.label?.() ?? props.label),
            slots.description?.() ??
              (props.description ? h("span", props.description) : null),
          ]),
        ],
      );
    };
  },
});

const NuxtCheckboxGroup = defineComponent({
  name: "NuxtCheckboxGroup",
  inheritAttrs: false,
  props: {
    modelValue: { type: Array as () => unknown[], default: () => [] },
    items: {
      type: Array as () => Array<Record<string, unknown>>,
      default: () => [],
    },
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
    return () =>
      h(
        "div",
        {
          ...attrs,
          "data-slot": attrs["data-slot"] ?? "checkbox-group",
          class: props.ui.root,
        },
        [
          h("fieldset", { "data-slot": "fieldset", class: props.ui.fieldset }, [
            props.legend || slots.legend
              ? h(
                  "legend",
                  { "data-slot": "legend", class: props.ui.legend },
                  slots.legend?.() ?? props.legend,
                )
              : null,
            ...props.items.map((item) => {
              const value = item[props.valueKey];
              const checked = props.modelValue.includes(value);
              const dataAttrs = Object.fromEntries(
                Object.entries(item).filter(([key]) => key.startsWith("data-")),
              );
              return h(
                "div",
                { ...dataAttrs, "data-slot": "item", class: props.ui.item },
                [
                  h("button", {
                    type: "button",
                    role: "checkbox",
                    disabled: props.disabled || Boolean(item.disabled),
                    "aria-checked": String(checked),
                    class: props.ui.base,
                    onClick: () => toggle(item),
                  }),
                  h("span", { "data-slot": "wrapper" }, [
                    h(
                      "span",
                      { "data-slot": "label" },
                      slots.label?.({ item }) ??
                        String(item[props.labelKey] ?? ""),
                    ),
                    item[props.descriptionKey]
                      ? h(
                          "span",
                          { "data-slot": "description" },
                          slots.description?.({ item }) ??
                            String(item[props.descriptionKey]),
                        )
                      : null,
                  ]),
                ],
              );
            }),
          ]),
        ],
      );
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
    return () =>
      h(
        "div",
        { "data-slot": attrs["data-slot"] ?? "switch", class: props.ui.root },
        [
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
        ],
      );
  },
});

const NuxtCard = defineComponent({
  name: "NuxtCard",
  inheritAttrs: false,
  props: {
    as: { type: String, default: "div" },
    ui: { type: Object as () => Record<string, string>, default: () => ({}) },
  },
  setup(props, { attrs, slots }) {
    return () =>
      h(props.as, { ...attrs, class: [attrs.class, props.ui.root] }, [
        slots.header
          ? h("div", { "data-slot": "header" }, slots.header())
          : null,
        h(
          "div",
          { "data-slot": "body", class: props.ui.body },
          slots.default?.(),
        ),
        slots.footer
          ? h("div", { "data-slot": "footer" }, slots.footer())
          : null,
      ]);
  },
});

const NuxtButton = defineComponent({
  name: "NuxtButton",
  inheritAttrs: false,
  props: {
    label: String,
    icon: String,
    trailingIcon: String,
    type: { type: String, default: "button" },
    disabled: Boolean,
    loading: Boolean,
    to: [String, Object],
    href: String,
    ui: { type: Object as () => Record<string, string>, default: () => ({}) },
  },
  emits: ["click"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        props.to || props.href ? "a" : "button",
        {
          ...attrs,
          ...(props.to || props.href
            ? {
                href:
                  typeof props.to === "string" ? props.to : (props.href ?? "#"),
              }
            : {}),
          type: props.type,
          disabled: props.disabled || props.loading,
          class: [attrs.class, props.ui.base],
          onClick: (event: MouseEvent) => emit("click", event),
        },
        [
          props.icon
            ? h("span", { "aria-hidden": "true", "data-icon": props.icon })
            : null,
          slots.leading?.(),
          slots.default?.() ??
            (props.label
              ? h("span", { class: props.ui.label }, props.label)
              : null),
          slots.trailing?.(),
          props.trailingIcon
            ? h("span", {
                "aria-hidden": "true",
                "data-icon": props.trailingIcon,
              })
            : null,
        ],
      );
  },
});

const NuxtBadge = defineComponent({
  name: "NuxtBadge",
  inheritAttrs: false,
  props: { label: String },
  setup(props, { attrs, slots }) {
    return () => h("span", attrs, slots.default?.() ?? props.label);
  },
});

const NuxtProgress = defineComponent({
  name: "NuxtProgress",
  inheritAttrs: false,
  props: {
    modelValue: { type: Number, default: 0 },
    max: { type: Number, default: 100 },
  },
  setup(props, { attrs, slots }) {
    return () =>
      h("div", attrs, [
        slots.status?.({ percent: props.modelValue }),
        h("div", {
          role: "progressbar",
          "aria-valuemin": "0",
          "aria-valuemax": String(props.max),
          "aria-valuenow": String(props.modelValue),
        }),
      ]);
  },
});

const NuxtAlert = defineComponent({
  name: "NuxtAlert",
  inheritAttrs: false,
  props: {
    title: String,
    description: String,
    actions: {
      type: Array as () => Array<Record<string, unknown>>,
      default: () => [],
    },
    close: [Boolean, Object],
  },
  emits: ["update:open"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        "div",
        { role: attrs.color === "error" ? "alert" : "status", ...attrs },
        [
          slots.title?.() ?? (props.title ? h("p", props.title) : null),
          slots.description?.() ??
            (props.description ? h("p", props.description) : null),
          slots.default?.(),
          slots.actions?.(),
          ...props.actions.map((action) =>
            h(
              "button",
              {
                ...itemDataAttrs(action),
                ...(action.to ? { to: String(action.to) } : {}),
                type: "button",
                disabled: Boolean(action.disabled),
                onClick: (event: Event) => {
                  if (typeof action.onClick === "function")
                    action.onClick(event);
                  if (typeof action.onSelect === "function")
                    action.onSelect(event);
                },
              },
              String(action.label ?? ""),
            ),
          ),
          props.close
            ? h(
                "button",
                {
                  type: "button",
                  "aria-label":
                    typeof props.close === "object" && props.close
                      ? ((props.close as Record<string, unknown>)[
                          "aria-label"
                        ] ?? (props.close as Record<string, unknown>).label)
                      : "Fechar",
                  onClick: () => emit("update:open", false),
                },
                "Fechar",
              )
            : null,
        ],
      );
  },
});

const NuxtPopover = defineComponent({
  name: "NuxtPopover",
  inheritAttrs: false,
  // Como o Popover real: controlado por `v-model:open` quando o pai o liga; senão,
  // o próprio toque no gatilho abre e fecha.
  props: { open: { type: Boolean, default: undefined } },
  emits: ["update:open"],
  setup(props, { attrs, emit, slots }) {
    const inner = ref(false);
    const isOpen = () => (props.open === undefined ? inner.value : props.open);
    return () =>
      h("div", { ...attrs, "data-open": String(isOpen()) }, [
        h(
          "span",
          {
            onClick: () => {
              if (props.open === undefined) inner.value = !inner.value;
              emit("update:open", !isOpen());
            },
          },
          slots.default?.(),
        ),
        isOpen() ? slots.content?.() : null,
      ]);
  },
});

const NuxtDrawer = defineComponent({
  name: "NuxtDrawer",
  inheritAttrs: false,
  props: { open: Boolean },
  emits: ["update:open"],
  setup(props, { attrs, slots }) {
    return () =>
      props.open
        ? h("div", { role: "dialog", ...attrs }, [
            slots.header?.(),
            slots.body?.(),
            slots.footer?.(),
          ])
        : null;
  },
});

const NuxtModal = defineComponent({
  name: "NuxtModal",
  inheritAttrs: false,
  props: { open: Boolean, title: String, description: String },
  emits: ["update:open"],
  setup(props, { attrs, slots }) {
    return () =>
      props.open
        ? h("div", { role: "dialog", ...attrs }, [
            props.title ? h("h2", props.title) : null,
            props.description ? h("p", props.description) : null,
            slots.body?.(),
            slots.footer?.(),
          ])
        : null;
  },
});

const NuxtTabs = defineComponent({
  name: "NuxtTabs",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "0" },
    items: {
      type: Array as () => Array<Record<string, unknown>>,
      default: () => [],
    },
    valueKey: { type: String, default: "value" },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        "div",
        { ...attrs, role: "tablist" },
        props.items.map((item, index) => {
          const value = item[props.valueKey] ?? String(index);
          return h(
            "button",
            {
              type: "button",
              role: "tab",
              "aria-selected": String(value === props.modelValue),
              onClick: () => emit("update:modelValue", value),
            },
            slots.default?.({ item, index }) ?? String(item.label ?? ""),
          );
        }),
      );
  },
});

const NuxtInput = defineComponent({
  name: "NuxtInput",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "" },
    type: { type: String, default: "text" },
    disabled: Boolean,
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    const fieldLabel = inject<{ label?: string } | undefined>(
      formFieldLabelKey,
      undefined,
    );
    return () =>
      h("input", {
        ...attrs,
        "aria-label": attrs["aria-label"] ?? fieldLabel?.label,
        type: props.type,
        value: props.modelValue,
        disabled: props.disabled,
        onInput: (event: Event) =>
          emit("update:modelValue", (event.target as HTMLInputElement).value),
      });
  },
});

const NuxtInputNumber = defineComponent({
  name: "NuxtInputNumber",
  inheritAttrs: false,
  props: {
    modelValue: { type: Number, default: 0 },
    disabled: Boolean,
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    const fieldLabel = inject<{ label?: string } | undefined>(
      formFieldLabelKey,
      undefined,
    );
    return () =>
      h("div", attrs, [
        h(
          "button",
          {
            type: "button",
            "aria-label": "Um volume a menos",
            disabled: props.disabled,
            onClick: () => emit("update:modelValue", props.modelValue - 1),
          },
          "−",
        ),
        h("input", {
          "aria-label": attrs["aria-label"] ?? fieldLabel?.label,
          type: "number",
          value: props.modelValue,
          disabled: props.disabled,
          onInput: (event: Event) =>
            emit(
              "update:modelValue",
              Number((event.target as HTMLInputElement).value),
            ),
        }),
        String(props.modelValue),
        h(
          "button",
          {
            type: "button",
            "aria-label": "Um volume a mais",
            disabled: props.disabled,
            onClick: () => emit("update:modelValue", props.modelValue + 1),
          },
          "+",
        ),
      ]);
  },
});

const NuxtTextarea = defineComponent({
  name: "NuxtTextarea",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "" },
    disabled: Boolean,
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    const fieldLabel = inject<{ label?: string } | undefined>(
      formFieldLabelKey,
      undefined,
    );
    return () =>
      h("textarea", {
        ...attrs,
        "aria-label": attrs["aria-label"] ?? fieldLabel?.label,
        value: props.modelValue,
        disabled: props.disabled,
        onInput: (event: Event) =>
          emit(
            "update:modelValue",
            (event.target as HTMLTextAreaElement).value,
          ),
      });
  },
});

// Fiel ao Nuxt UI/reka-ui em duas coisas que já esconderam defeito: item com
// `value: ""` lança (o SelectItem real lança e derruba a página) e o convite é a
// prop `placeholder`, sem item próprio.
const NuxtSelect = defineComponent({
  name: "NuxtSelect",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number, Boolean], default: "" },
    items: { type: Array as () => Array<unknown>, default: () => [] },
    placeholder: { type: String, default: "" },
    disabled: Boolean,
    valueKey: { type: String, default: "value" },
    labelKey: { type: String, default: "label" },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    const fieldLabel = inject<{ label?: string } | undefined>(
      formFieldLabelKey,
      undefined,
    );
    return () =>
      h(
        "select",
        {
          ...attrs,
          "aria-label": attrs["aria-label"] ?? fieldLabel?.label,
          value: props.modelValue ?? "",
          disabled: props.disabled,
          onChange: (event: Event) =>
            emit(
              "update:modelValue",
              (event.target as HTMLSelectElement).value,
            ),
        },
        [
          ...(props.placeholder
            ? [h("option", { value: "", disabled: true, hidden: true }, props.placeholder)]
            : []),
          ...props.items.map((entry) => {
            const item =
              typeof entry === "object" && entry !== null
                ? (entry as Record<string, unknown>)
                : null;
            const value = item ? item[props.valueKey] : entry;
            const label = item ? item[props.labelKey] : entry;
            if (value === "")
              throw new Error(
                "A <SelectItem /> must have a value prop that is not an empty string.",
              );
            return h(
              "option",
              { value, disabled: Boolean(item?.disabled) },
              String(label ?? ""),
            );
          }),
        ],
      );
  },
});

const NuxtFormField = defineComponent({
  name: "NuxtFormField",
  inheritAttrs: false,
  props: {
    label: String,
    hint: String,
    description: String,
    error: [String, Boolean],
  },
  setup(props, { attrs, slots }) {
    provide(formFieldLabelKey, props);
    return () =>
      h("div", attrs, [
        props.label || slots.label
          ? h("label", slots.label?.() ?? props.label)
          : null,
        props.hint || slots.hint
          ? h("span", slots.hint?.() ?? props.hint)
          : null,
        slots.default?.(),
        props.description || slots.description
          ? h("p", slots.description?.() ?? props.description)
          : null,
        props.error ? h("p", { role: "alert" }, String(props.error)) : null,
      ]);
  },
});

const NuxtForm = defineComponent({
  name: "NuxtForm",
  inheritAttrs: false,
  props: { state: { type: Object, default: () => ({}) } },
  emits: ["submit"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        "form",
        {
          ...attrs,
          onSubmit: (event: SubmitEvent) => {
            event.preventDefault();
            emit("submit", { data: props.state });
          },
        },
        slots.default?.(),
      );
  },
});

const NuxtTable = defineComponent({
  name: "NuxtTable",
  inheritAttrs: false,
  props: {
    data: {
      type: Array as () => Array<Record<string, unknown>>,
      default: () => [],
    },
    columns: {
      type: Array as () => Array<{
        id?: string;
        accessorKey?: string;
        header?: string;
      }>,
      default: () => [],
    },
    caption: String,
  },
  setup(props, { attrs, slots }) {
    return () =>
      h("table", attrs, [
        props.caption ? h("caption", props.caption) : null,
        h(
          "tbody",
          props.data.map((original, rowIndex) =>
            h(
              "tr",
              { key: rowIndex },
              props.columns.map((column, columnIndex) => {
                const id =
                  column.id ?? column.accessorKey ?? String(columnIndex);
                const cell = slots[`${id}-cell`];
                return h(
                  "td",
                  { key: id },
                  cell?.({ row: { original }, index: rowIndex }) ??
                    String(original[column.accessorKey ?? id] ?? ""),
                );
              }),
            ),
          ),
        ),
      ]);
  },
});

const itemDataAttrs = (item: Record<string, unknown>) =>
  Object.fromEntries(
    Object.entries(item).filter(([key]) => key.startsWith("data-")),
  );

const menuItems = (
  entries: unknown[],
  slots: Record<string, ((scope: unknown) => unknown) | undefined>,
) => {
  const flat = entries.flatMap((entry) =>
    Array.isArray(entry) ? entry : [entry],
  );
  return flat.map((entry, index) => {
    const item = entry as Record<string, unknown>;
    const slotName = typeof item.slot === "string" ? item.slot : undefined;
    const content =
      slotName && slots[slotName]
        ? slots[slotName]?.({ item, index })
        : String(item.label ?? "");
    return h(
      "button",
      {
        ...itemDataAttrs(item),
        type: "button",
        disabled: Boolean(item.disabled),
        title: item.title,
        "aria-label": item["aria-label"] ?? item.label,
        onClick: (event: Event) => {
          if (typeof item.onSelect === "function") item.onSelect(event);
          if (typeof item.onClick === "function") item.onClick(event);
        },
      },
      content,
    );
  });
};

const NuxtNavigationMenu = defineComponent({
  name: "NuxtNavigationMenu",
  inheritAttrs: false,
  props: { items: { type: Array as () => unknown[], default: () => [] } },
  setup(props, { attrs, slots }) {
    return () => h("nav", attrs, menuItems(props.items, slots));
  },
});

// Como o real: os itens só existem com o menu aberto (o gatilho abre; escolher fecha).
const NuxtDropdownMenu = defineComponent({
  name: "NuxtDropdownMenu",
  inheritAttrs: false,
  props: { items: { type: Array as () => unknown[], default: () => [] } },
  setup(props, { attrs, slots }) {
    const open = ref(false);
    return () =>
      h("div", attrs, [
        h(
          "div",
          { onClickCapture: () => (open.value = !open.value) },
          slots.default?.(),
        ),
        open.value
          ? h(
              "div",
              { onClick: () => (open.value = false) },
              menuItems(props.items, slots),
            )
          : null,
      ]);
  },
});

const NuxtRadioGroup = defineComponent({
  name: "NuxtRadioGroup",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "" },
    items: { type: Array as () => Array<unknown>, default: () => [] },
    valueKey: { type: String, default: "value" },
    labelKey: { type: String, default: "label" },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h(
        "div",
        { ...attrs, role: "radiogroup" },
        props.items.map((item) => {
          const primitive = typeof item !== "object" || item === null;
          const record = primitive ? {} : (item as Record<string, unknown>);
          const value = primitive ? item : record[props.valueKey];
          return h(
            "button",
            {
              ...itemDataAttrs(record),
              type: "button",
              role: "radio",
              disabled: Boolean(record.disabled),
              "aria-checked": String(value === props.modelValue),
              onClick: () => emit("update:modelValue", value),
            },
            String(primitive ? item : (record[props.labelKey] ?? "")),
          );
        }),
      );
  },
});

const NuxtSlideover = defineComponent({
  name: "NuxtSlideover",
  inheritAttrs: false,
  props: { open: Boolean, title: String, description: String },
  emits: ["update:open"],
  setup(props, { attrs, slots }) {
    return () =>
      props.open
        ? h("div", { role: "dialog", ...attrs }, [
            props.title ? h("h2", props.title) : null,
            props.description ? h("p", props.description) : null,
            slots.header?.(),
            slots.body?.(),
            slots.footer?.(),
          ])
        : null;
  },
});

const NuxtLink = defineComponent({
  name: "NuxtLink",
  inheritAttrs: false,
  props: { to: [String, Object], href: String },
  setup(props, { attrs, slots }) {
    return () =>
      h(
        "a",
        {
          ...attrs,
          href: typeof props.to === "string" ? props.to : (props.href ?? "#"),
        },
        slots.default?.(),
      );
  },
});

const NuxtCollapsible = defineComponent({
  name: "NuxtCollapsible",
  setup(_, { attrs, slots }) {
    return () => h("div", attrs, [slots.default?.(), slots.content?.()]);
  },
});

const textPrimitive = (name: string, tag = "div") =>
  defineComponent({
    name,
    inheritAttrs: false,
    props: { title: String, description: String, label: String },
    setup(props, { attrs, slots }) {
      return () =>
        h(tag, attrs, [
          slots.default?.() ?? props.label,
          props.title ? h("p", props.title) : null,
          props.description ? h("p", props.description) : null,
          slots.actions?.(),
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
  NuxtCard,
  NuxtButton,
  NuxtBadge,
  NuxtProgress,
  NuxtAlert,
  NuxtPopover,
  NuxtDrawer,
  NuxtModal,
  NuxtTabs,
  NuxtInput,
  NuxtInputNumber,
  NuxtTextarea,
  NuxtSelect,
  NuxtForm,
  NuxtFormField,
  NuxtTable,
  NuxtNavigationMenu,
  NuxtDropdownMenu,
  NuxtRadioGroup,
  NuxtSlideover,
  NuxtCollapsible,
  NuxtAvatar: textPrimitive("NuxtAvatar", "span"),
  NuxtChip: textPrimitive("NuxtChip", "span"),
  NuxtEmpty: textPrimitive("NuxtEmpty"),
  NuxtKbd: textPrimitive("NuxtKbd", "kbd"),
  NuxtLink,
  NuxtSkeleton: textPrimitive("NuxtSkeleton"),
  NuxtTimeline: textPrimitive("NuxtTimeline"),
  OperatorOrderDetail,
  OperatorMoreMenu,
  OperatorTimedButton,
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
