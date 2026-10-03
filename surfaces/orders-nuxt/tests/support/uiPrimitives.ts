import { config } from "@vue/test-utils";

// O interruptor entra de VERDADE, não como stub: ele vive no operator-kit e é SFC
// puro (nenhum runtime Nuxt). Stubar seria justamente apagar o contrato que estes
// testes cobram — `role="switch"` e `aria-checked` —, e foi um trilho escrito à mão
// nesta mesma tela que motivou a promoção. Mesmo arranjo do Marketing
// (`marketing-nuxt/tests/support/uiPrimitives.ts`).
import UiSwitch from "../../../operator-kit/app/components/UiSwitch.vue";
// O detalhe do pedido também entra de verdade: é o kit que desenha as seções do
// `pages/[ref].vue` (a mesma tela do detalhe da encomenda no PDV), e stubá-lo
// apagaria justamente o que os testes da página cobram.
import OperatorOrderDetail from "../../../operator-kit/app/components/OperatorOrderDetail.vue";
// O grupo de rádio da vocação (painel do produto) entra de verdade pelo mesmo
// motivo: o contrato cobrado é `role="radio"`/`aria-checked` do kit.
import UiRadio from "../../../operator-kit/app/components/UiRadio.vue";
import UiRadioGroup from "../../../operator-kit/app/components/UiRadioGroup.vue";

config.global.components = {
  ...config.global.components,
  UiSwitch,
  OperatorOrderDetail,
  UiRadio,
  UiRadioGroup,
};
