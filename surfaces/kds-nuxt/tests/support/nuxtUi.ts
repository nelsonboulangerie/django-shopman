import { defineComponent, h } from "vue";

// Peças do Nuxt UI nos testes de componente da Cozinha (sem runtime Nuxt, ver
// vitest.config.ts). O que se testa é a tela: o rótulo, o toque e o atributo de cada
// botão. O desenho de cada peça é do Nuxt UI e do kit (testados lá).

/** `NuxtButton`: um `<button>` com o rótulo (ou o slot), a cor e a variante em `data-*`. */
export const NuxtButton = defineComponent({
  name: "NuxtButton",
  inheritAttrs: false,
  props: {
    label: String,
    icon: String,
    color: { type: String, default: "primary" },
    variant: { type: String, default: "solid" },
    size: String,
    to: String,
    disabled: Boolean,
    loading: Boolean,
    block: Boolean,
    ui: Object,
  },
  emits: ["click"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        "button",
        {
          ...attrs,
          type: "button",
          disabled: props.disabled || undefined,
          "data-color": props.color,
          "data-variant": props.variant,
          "data-icon": props.icon,
          onClick: (event: MouseEvent) => emit("click", event),
        },
        slots.default ? slots.default() : props.label,
      );
  },
});

/** `NuxtModal`/`NuxtDrawer`: abertos, mostram título, descrição e os slots. */
function overlay(name: string) {
  return defineComponent({
    name,
    inheritAttrs: false,
    props: { open: Boolean, title: String, description: String, ui: Object },
    emits: ["update:open"],
    setup(props, { attrs, slots }) {
      return () =>
        props.open
          ? h("div", { ...attrs, role: "dialog" }, [
              props.title ? h("h2", props.title) : null,
              props.description ? h("p", props.description) : null,
              slots.content?.(),
              slots.body?.(),
            ])
          : null;
    },
  });
}
export const NuxtModal = overlay("NuxtModal");
export const NuxtDrawer = overlay("NuxtDrawer");

export const nuxtUiStubs = { NuxtButton, NuxtModal, NuxtDrawer };
