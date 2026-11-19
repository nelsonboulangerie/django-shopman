<script setup lang="ts">
// As saídas de uma promessa em risco (WP-G08): "Avisar o cliente", "Remarcar no PDV",
// "Cancelar pedido" e, quando a Produção ainda resolve, "Abrir a Produção". Os nomes, a
// ordem, o destino, a guarda e QUAL é a recomendada vêm do servidor
// (`promise.actions`); aqui cada uma vira um botão, e só a recomendada é cheia. No
// cartão e nas listas são atalhos: o contato do cliente e o cancelar com motivo moram
// no detalhe do pedido; remarcar mora no PDV e o plano, na Produção, que abrem na
// janela deles (`useOperatorAppLink`).
//
// Sem raiz própria: quem chama dá o lugar (as ações do aviso, a linha da Fila).
import { computed } from "vue";

import {
  exitButtons,
  type ExitTone,
  type PromiseExit,
} from "~/presentation/orderPromise";
import { useOperatorAppLink } from "../../../operator-kit/app/composables/useOperatorAppLink";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    exits: PromiseExit[];
    /** O código curto do pedido ("W33"), para o nome acessível de cada botão. */
    code: string;
    tone?: ExitTone;
  }>(),
  { tone: "row" },
);

const { attrsFor } = useOperatorAppLink();
const buttons = computed(() =>
  exitButtons(props.exits, props.tone).map((button) => ({
    ...button,
    link: button.external ? attrsFor(button.href) : null,
  })),
);
</script>

<template>
  <NuxtButton
    v-for="button in buttons"
    :key="button.ref"
    :to="button.disabled ? undefined : button.href"
    :target="button.link?.target"
    :rel="button.link?.rel"
    :external="button.external || undefined"
    :disabled="button.disabled"
    :icon="button.disabled ? 'i-lucide-lock' : button.icon"
    :label="button.label"
    :color="button.color"
    :variant="button.variant"
    class="max-sm:justify-center"
    :aria-label="`${button.label}: pedido ${code}`"
    :data-promise-exit="button.ref"
  />
</template>
