import { config } from "@vue/test-utils";
import { Fragment, defineComponent, h, inject, provide } from "vue";

// O interruptor entra de VERDADE, não como stub: ele vive no operator-kit e é SFC
// puro (nenhum runtime Nuxt). Stubar seria justamente apagar o contrato que estes
// testes cobram — `role="switch"` e `aria-checked` —, e foi um trilho escrito à mão
// nesta mesma tela que motivou a promoção. Mesmo arranjo do Marketing
// (`marketing-nuxt/tests/support/uiPrimitives.ts`).
import UiSwitch from "../../../operator-kit/app/components/UiSwitch.vue";
import UiCheckbox from "../../../operator-kit/app/components/UiCheckbox.vue";
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

config.global.components = {
  ...config.global.components,
  UiSwitch,
  UiCheckbox,
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
