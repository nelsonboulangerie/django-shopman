import { config } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";

// Os primitivos de ESCOLHA entram de verdade, não como stub: eles vivem no
// operator-kit e são SFC puro (nenhum runtime Nuxt, só o `Icon`, que cada teste já
// stuba). Stub de checkbox/rádio/select seria justamente o lugar onde o contrato
// que interessa — `aria-checked`, `mixed`, teclado — deixaria de ser testado aqui.
import UiCheckbox from "../../../operator-kit/app/components/UiCheckbox.vue";
import UiCheckboxGroup from "../../../operator-kit/app/components/UiCheckboxGroup.vue";
import UiRadio from "../../../operator-kit/app/components/UiRadio.vue";
import UiRadioGroup from "../../../operator-kit/app/components/UiRadioGroup.vue";
import UiSelect from "../../../operator-kit/app/components/UiSelect.vue";
import UiSwitch from "../../../operator-kit/app/components/UiSwitch.vue";
import UiTabs from "../../../operator-kit/app/components/Ui/Tabs/Tabs.vue";
import UiTabsList from "../../../operator-kit/app/components/Ui/Tabs/List.vue";
import UiTabsTrigger from "../../../operator-kit/app/components/Ui/Tabs/Trigger.vue";
import UiToggleChip from "../../../operator-kit/app/components/UiToggleChip.vue";

function invoke(listener: unknown, event: Event) {
  if (Array.isArray(listener)) {
    for (const candidate of listener) invoke(candidate, event);
    return;
  }
  if (typeof listener === "function") listener(event);
}

// O projeto `component` roda sem o runtime Nuxt. Checkbox e switch continuam
// sendo os wrappers REAIS do operator-kit; estes dois dublês representam apenas
// a infraestrutura Nuxt UI/Reka abaixo deles, com o mesmo contrato observável
// (slots, role, aria-checked e v-model). Assim a suíte não transforma uma peça
// canônica em tag desconhecida e deixa de testar silenciosamente o formulário.
const NuxtSwitch = defineComponent({
  name: "NuxtSwitch",
  inheritAttrs: false,
  props: {
    modelValue: Boolean,
    disabled: Boolean,
    ui: { type: Object, default: () => ({}) },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h(
        "div",
        {
          "data-slot": attrs["data-slot"] ?? "switch",
          class: ["relative flex", props.ui.root],
        },
        h(
          "button",
          {
            ...attrs,
            "data-slot": "base",
            role: "switch",
            type: "button",
            disabled: props.disabled,
            "aria-checked": String(props.modelValue),
            "data-state": props.modelValue ? "checked" : "unchecked",
            class: props.ui.base,
            onClick: () => emit("update:modelValue", !props.modelValue),
          },
          h("span", { "data-slot": "thumb" }),
        ),
      );
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
    ui: { type: Object, default: () => ({}) },
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

// O mesmo limite vale para o SelectMenu: este dublê é somente a infraestrutura
// Nuxt UI abaixo do UiSelect real. O comportamento completo de foco, portal e
// teclado permanece coberto no operator-kit; aqui preservamos o contrato que os
// formulários do Marketing dirigem (gatilho, busca, opções e v-model).
const NuxtSelectMenu = defineComponent({
  name: "NuxtSelectMenu",
  inheritAttrs: false,
  props: {
    modelValue: {
      type: Object as () => Record<string, unknown>,
      default: undefined,
    },
    items: {
      type: Array as () => Array<Record<string, unknown>>,
      default: () => [],
    },
    disabled: Boolean,
    placeholder: String,
    searchInput: { type: [Boolean, Object], default: false },
    ui: { type: Object, default: () => ({}) },
  },
  emits: ["update:modelValue", "update:searchTerm", "highlight"],
  setup(props, { attrs, emit, expose, slots }) {
    const open = ref(false);
    const triggerRef = ref<HTMLButtonElement>();
    expose({ triggerRef });

    const choose = (item: Record<string, unknown>) => {
      if (item.disabled) return;
      emit("update:modelValue", item);
      open.value = false;
    };

    return () =>
      h("div", { "data-slot": "select-menu" }, [
        h(
          "button",
          {
            ...attrs,
            ref: triggerRef,
            type: "button",
            disabled: props.disabled,
            role: "combobox",
            "aria-haspopup": "listbox",
            "aria-expanded": String(open.value),
            class: [props.ui.base, attrs.class],
            onClick: () => {
              if (!props.disabled) open.value = !open.value;
            },
          },
          slots.default?.() ?? props.placeholder,
        ),
        open.value
          ? h("div", { role: "listbox", "data-dismissable-layer": "" }, [
              props.searchInput
                ? h("input", {
                    ...(props.searchInput as Record<string, unknown>),
                    role: "combobox",
                    onInput: (event: Event) =>
                      emit(
                        "update:searchTerm",
                        (event.target as HTMLInputElement).value,
                      ),
                  })
                : null,
              props.items.length
                ? props.items.map((item) =>
                    h(
                      "button",
                      {
                        key: String(item.value),
                        type: "button",
                        role: "option",
                        "aria-selected": String(item === props.modelValue),
                        "aria-disabled": item.disabled ? "true" : undefined,
                        "data-slot": "item",
                        onMouseenter: () => emit("highlight", { value: item }),
                        onClick: () => choose(item),
                      },
                      slots.item?.({ item }) ??
                        String(item.label ?? item.value),
                    ),
                  )
                : h("div", { "data-slot": "empty" }, slots.empty?.()),
            ])
          : null,
      ]);
  },
});

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

// Os componentes canônicos de data/hora são exercitados com Nuxt UI/Reka no
// operator-kit. Aqui o dublê mantém o contrato string que a regra de Marketing
// consome, para estes testes continuarem focados em timezone, DST e payload.
function temporalInput(name: string, type: "date" | "time" | "datetime-local") {
  return defineComponent({
    name,
    inheritAttrs: false,
    props: { modelValue: { type: String, default: "" } },
    emits: ["update:modelValue"],
    setup(props, { attrs, emit }) {
      return () =>
        h("input", {
          ...attrs,
          type,
          value: props.modelValue,
          onInput: (event: Event) =>
            emit("update:modelValue", (event.target as HTMLInputElement).value),
        });
    },
  });
}

const UiDateField = temporalInput("UiDateField", "date");
const UiDateTimeField = temporalInput("UiDateTimeField", "datetime-local");
const UiTimeField = temporalInput("UiTimeField", "time");

const UiDateRangeField = defineComponent({
  name: "UiDateRangeField",
  inheritAttrs: false,
  props: {
    modelValue: {
      type: Object as () => { start?: string; end?: string },
      default: () => ({ start: "", end: "" }),
    },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h("div", { ...attrs, role: "group" }, [
        h("input", {
          "aria-label": "Início do período",
          type: "date",
          value: props.modelValue.start ?? "",
          onInput: (event: Event) =>
            emit("update:modelValue", {
              start: (event.target as HTMLInputElement).value,
              end: props.modelValue.end ?? "",
            }),
        }),
        h("input", {
          "aria-label": "Fim do período",
          type: "date",
          value: props.modelValue.end ?? "",
          onInput: (event: Event) =>
            emit("update:modelValue", {
              start: props.modelValue.start ?? "",
              end: (event.target as HTMLInputElement).value,
            }),
        }),
      ]);
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

// O NuxtStepper é validado no próprio operator-kit. Aqui o dublê preserva o
// contrato público consumido pelo formulário: nome, etapa atual, bloqueio e
// atualização controlada. Assim os testes de Campanhas continuam testando o
// fluxo, sem remontar o runtime Nuxt UI dentro de cada unitário do app.
const UiStepper = defineComponent({
  name: "UiStepper",
  props: {
    modelValue: { type: Number, default: 0 },
    items: {
      type: Array as () => Array<{
        title: string;
        description?: string;
        disabled?: boolean;
      }>,
      default: () => [],
    },
    label: { type: String, default: "Etapas" },
  },
  emits: ["update:modelValue"],
  setup(props, { emit }) {
    const choose = (index: number, item: { disabled?: boolean }) => {
      if (!item.disabled) emit("update:modelValue", index);
    };

    return () =>
      h(
        "div",
        {
          role: "group",
          "aria-label": props.label,
          "data-slot": "stepper-shell",
        },
        [
          h(
            "ol",
            props.items.map((item, index) =>
              h("li", [
                h(
                  "button",
                  {
                    type: "button",
                    disabled: item.disabled,
                    "aria-current":
                      props.modelValue === index ? "step" : undefined,
                    "aria-label": `${index + 1}. ${item.title}`,
                    onClick: () => choose(index, item),
                    onMousedown: (event: MouseEvent) => {
                      if (event.button === 0 && !event.ctrlKey)
                        choose(index, item);
                    },
                  },
                  item.title,
                ),
              ]),
            ),
          ),
        ],
      );
  },
});

config.global.components = {
  ...config.global.components,
  NuxtCheckbox,
  NuxtCheckboxGroup,
  NuxtSelectMenu,
  NuxtSwitch,
  UiButton,
  UiCheckbox,
  UiCheckboxGroup,
  UiDateField,
  UiDateRangeField,
  UiDateTimeField,
  UiInput,
  UiRadio,
  UiRadioGroup,
  UiSelect,
  UiSwitch,
  UiStepper,
  UiTabs,
  UiTabsList,
  UiTabsTrigger,
  UiTextarea,
  UiTimeField,
  UiToggleChip,
};
