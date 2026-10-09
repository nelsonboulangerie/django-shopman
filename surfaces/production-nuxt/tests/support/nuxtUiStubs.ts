import { defineComponent, h, mergeProps, ref, type PropType } from "vue";

// Os testes de componente da Produção rodam sem o runtime Nuxt (ver vitest.config.ts).
// Estes stubs são as peças do Nuxt UI que as telas usam, reduzidas ao contrato que os
// testes cobram: continuam sendo elementos reais (um botão é um `<button>`), repassam
// attrs e listeners, e mantêm o `v-model` (`modelValue`, `open`) das peças oficiais.
// Diálogos e folhas desenham o conteúdo NO LUGAR quando abertos (sem teleport), para
// que o teste consulte o que a pessoa veria.

type Item = Record<string, unknown>;

/** `NuxtButton`: `<a>` com `to`/`href`, `<button>` no resto; `label` ou slot. */
export const NuxtButtonStub = defineComponent({
  name: "NuxtButton",
  inheritAttrs: false,
  props: {
    label: { type: String, default: undefined },
    to: { type: [String, Object], default: undefined },
    href: { type: String, default: undefined },
    type: { type: String, default: "button" },
    disabled: Boolean,
    loading: Boolean,
    icon: { type: String, default: undefined },
    trailingIcon: { type: String, default: undefined },
    color: { type: String, default: undefined },
    variant: { type: String, default: undefined },
    size: { type: String, default: undefined },
    block: Boolean,
    square: Boolean,
  },
  setup(props, { attrs, slots }) {
    return () => {
      const content = [
        slots.leading?.(),
        slots.default?.() ?? props.label,
        slots.trailing?.(),
      ];
      const shared = {
        "data-color": props.color,
        "data-variant": props.variant,
        "data-size": props.size,
        "data-icon": props.icon,
      };
      if (props.to !== undefined || props.href !== undefined) {
        return h(
          "a",
          mergeProps(attrs, shared, {
            href: typeof props.to === "string" ? props.to : props.href,
            "aria-disabled": props.disabled || undefined,
          }),
          content,
        );
      }
      return h(
        "button",
        mergeProps(attrs, shared, {
          type: props.type,
          disabled: props.disabled || props.loading,
          "aria-busy": props.loading || undefined,
        }),
        content,
      );
    };
  },
});

export const NuxtBadgeStub = defineComponent({
  name: "NuxtBadge",
  inheritAttrs: false,
  props: { label: { type: [String, Number], default: undefined }, color: String },
  setup(props, { attrs, slots }) {
    return () =>
      h("span", mergeProps(attrs, { "data-color": props.color }), [
        slots.leading?.(),
        slots.default?.() ?? props.label,
        slots.trailing?.(),
      ]);
  },
});

export const NuxtInputStub = defineComponent({
  name: "NuxtInput",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "" },
    type: { type: String, default: "text" },
    disabled: Boolean,
    placeholder: String,
  },
  emits: ["update:modelValue", "blur", "focus", "change"],
  setup(props, { attrs, emit, expose }) {
    const inputRef = ref<HTMLInputElement | null>(null);
    expose({ inputRef });
    return () =>
      h(
        "input",
        mergeProps(attrs, {
          ref: inputRef,
          type: props.type,
          disabled: props.disabled,
          placeholder: props.placeholder,
          value: props.modelValue,
          onInput: (event: Event) =>
            emit("update:modelValue", (event.target as HTMLInputElement).value),
        }),
      );
  },
});

export const NuxtTextareaStub = defineComponent({
  name: "NuxtTextarea",
  inheritAttrs: false,
  props: {
    modelValue: { type: String, default: "" },
    disabled: Boolean,
    placeholder: String,
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h(
        "textarea",
        mergeProps(attrs, {
          disabled: props.disabled,
          placeholder: props.placeholder,
          value: props.modelValue,
          onInput: (event: Event) =>
            emit("update:modelValue", (event.target as HTMLTextAreaElement).value),
        }),
      );
  },
});

export const NuxtCheckboxStub = defineComponent({
  name: "NuxtCheckbox",
  inheritAttrs: false,
  props: {
    modelValue: { type: [Boolean, String], default: false },
    disabled: Boolean,
    label: String,
    description: String,
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, slots }) {
    return () => {
      const checked = props.modelValue === true;
      return h("div", { "data-slot": "checkbox" }, [
        h(
          "button",
          mergeProps(attrs, {
            type: "button",
            role: "checkbox",
            disabled: props.disabled,
            "aria-label": attrs["aria-label"] ?? props.label,
            "aria-checked": String(checked),
            onClick: () => emit("update:modelValue", !checked),
          }),
        ),
        h("label", slots.label?.() ?? props.label),
        slots.description?.() ?? (props.description ? h("span", props.description) : null),
      ]);
    };
  },
});

export const NuxtFormFieldStub = defineComponent({
  name: "NuxtFormField",
  inheritAttrs: false,
  props: { label: String, description: String, hint: String, help: String, error: [String, Boolean] },
  setup(props, { attrs, slots }) {
    return () =>
      h("div", attrs, [
        props.label || slots.label ? h("label", slots.label?.() ?? props.label) : null,
        props.description ? h("p", props.description) : null,
        slots.default?.(),
        props.help ? h("p", props.help) : null,
        typeof props.error === "string" ? h("p", { role: "alert" }, props.error) : null,
      ]);
  },
});

/** Diálogo e folhas (`NuxtModal`, `NuxtDrawer`, `NuxtSlideover`): conteúdo no lugar. */
function overlayStub(name: string) {
  return defineComponent({
    name,
    inheritAttrs: false,
    props: {
      open: { type: Boolean, default: undefined },
      title: String,
      description: String,
    },
    emits: ["update:open", "after:leave", "close:prevent"],
    setup(props, { attrs, emit, slots }) {
      const inner = ref(false);
      const isOpen = () => (props.open === undefined ? inner.value : props.open);
      const close = () => {
        inner.value = false;
        emit("update:open", false);
      };
      return () => [
        slots.default
          ? h(
              "span",
              {
                "data-overlay-trigger": "",
                onClick: () => {
                  inner.value = true;
                  emit("update:open", true);
                },
              },
              slots.default(),
            )
          : null,
        isOpen()
          ? h("div", mergeProps(attrs, { role: "dialog", "data-overlay": name }), [
              slots.content?.({ close }) ?? [
                slots.header?.({ close }) ??
                  [
                    props.title ? h("h2", props.title) : null,
                    props.description ? h("p", props.description) : null,
                  ],
                slots.body?.({ close }),
                slots.footer?.({ close }),
              ],
            ])
          : null,
      ];
    },
  });
}

export const NuxtModalStub = overlayStub("NuxtModal");
export const NuxtDrawerStub = overlayStub("NuxtDrawer");
export const NuxtSlideoverStub = overlayStub("NuxtSlideover");

/** `NuxtPopover`: gatilho + conteúdo quando aberto (controlado ou não). */
export const NuxtPopoverStub = defineComponent({
  name: "NuxtPopover",
  inheritAttrs: false,
  props: { open: { type: Boolean, default: undefined }, mode: String },
  emits: ["update:open"],
  setup(props, { attrs, emit, slots }) {
    const inner = ref(false);
    const isOpen = () => (props.open === undefined ? inner.value : props.open);
    const close = () => {
      inner.value = false;
      emit("update:open", false);
    };
    return () =>
      h("div", attrs, [
        h(
          "span",
          {
            "data-popover-trigger": "",
            onClick: () => {
              inner.value = !isOpen();
              emit("update:open", !isOpen());
            },
          },
          slots.default?.({ open: isOpen() }),
        ),
        slots.anchor?.(),
        isOpen() ? h("div", { "data-popover-content": "" }, slots.content?.({ close })) : null,
      ]);
  },
});

export const NuxtAlertStub = defineComponent({
  name: "NuxtAlert",
  inheritAttrs: false,
  props: {
    title: String,
    description: String,
    color: String,
    actions: { type: Array as PropType<Item[]>, default: () => [] },
  },
  setup(props, { attrs, slots }) {
    return () =>
      h("div", mergeProps(attrs, { role: "alert", "data-color": props.color }), [
        slots.title?.() ?? (props.title ? h("p", props.title) : null),
        slots.description?.() ?? (props.description ? h("p", props.description) : null),
        slots.actions?.() ??
          props.actions.map((action) =>
            h(
              "button",
              { type: "button", onClick: action.onClick as (() => void) | undefined },
              String(action.label ?? ""),
            ),
          ),
      ]);
  },
});

/** `NuxtTabs` sem conteúdo (`:content="false"`): uma aba é um botão `role="tab"`. */
export const NuxtTabsStub = defineComponent({
  name: "NuxtTabs",
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: undefined },
    items: { type: Array as PropType<Item[]>, default: () => [] },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h("div", mergeProps(attrs, { role: "tablist" }), [
        ...props.items.map((item, index) => {
          const value = (item.value ?? String(index)) as string | number;
          return h(
            "button",
            {
              type: "button",
              role: "tab",
              "aria-selected": String(value === props.modelValue),
              disabled: Boolean(item.disabled),
              onClick: () => emit("update:modelValue", value),
            },
            [String(item.label ?? ""), item.badge !== undefined ? ` ${String(item.badge)}` : ""],
          );
        }),
        slots.default?.(),
      ]);
  },
});

/** Menus (`NuxtDropdownMenu`, `NuxtContextMenu`): o gatilho e os itens como botões. */
function menuStub(name: string) {
  return defineComponent({
    name,
    inheritAttrs: false,
    props: {
      items: { type: Array as PropType<Item[] | Item[][]>, default: () => [] },
      open: { type: Boolean, default: undefined },
    },
    emits: ["update:open"],
    setup(props, { attrs, slots }) {
      return () => {
        const flat = (props.items as unknown[]).flat() as Item[];
        return h("div", mergeProps(attrs, { "data-menu": name }), [
          slots.default?.(),
          h(
            "div",
            { role: "menu" },
            flat
              .filter((item) => item.type !== "label" && item.type !== "separator")
              .map((item) =>
                h(
                  "button",
                  {
                    type: "button",
                    role: "menuitem",
                    disabled: Boolean(item.disabled),
                    onClick: (event: Event) =>
                      (item.onSelect as ((e: Event) => void) | undefined)?.(event),
                  },
                  String(item.label ?? ""),
                ),
              ),
          ),
        ]);
      };
    },
  });
}

export const NuxtDropdownMenuStub = menuStub("NuxtDropdownMenu");
export const NuxtContextMenuStub = menuStub("NuxtContextMenu");

/** Tudo de uma vez, para espalhar no `stubs` do teste. */
export const nuxtUiStubs = {
  NuxtButton: NuxtButtonStub,
  NuxtBadge: NuxtBadgeStub,
  NuxtInput: NuxtInputStub,
  NuxtTextarea: NuxtTextareaStub,
  NuxtCheckbox: NuxtCheckboxStub,
  NuxtFormField: NuxtFormFieldStub,
  NuxtModal: NuxtModalStub,
  NuxtDrawer: NuxtDrawerStub,
  NuxtSlideover: NuxtSlideoverStub,
  NuxtPopover: NuxtPopoverStub,
  NuxtAlert: NuxtAlertStub,
  NuxtTabs: NuxtTabsStub,
  NuxtDropdownMenu: NuxtDropdownMenuStub,
  NuxtContextMenu: NuxtContextMenuStub,
};
