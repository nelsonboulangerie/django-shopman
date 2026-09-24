import { config } from "@vue/test-utils";

// O interruptor entra de VERDADE, não como stub: ele vive no operator-kit e é SFC
// puro (nenhum runtime Nuxt). Stubar seria justamente apagar o contrato que estes
// testes cobram — `role="switch"` e `aria-checked` —, e foi um trilho escrito à mão
// nesta mesma tela que motivou a promoção. Mesmo arranjo do Marketing
// (`marketing-nuxt/tests/support/uiPrimitives.ts`).
import UiSwitch from "../../../operator-kit/app/components/UiSwitch.vue";

config.global.components = {
  ...config.global.components,
  UiSwitch,
};
