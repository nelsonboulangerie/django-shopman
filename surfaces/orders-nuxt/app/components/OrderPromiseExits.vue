<script setup lang="ts">
// As saídas de uma promessa em risco (WP-G08): "Resolver" e, quando a Produção ainda
// resolve, "Abrir a Produção". Os nomes, a ordem, a guarda e QUAL é a recomendada vêm
// do servidor (`promise.actions`); aqui cada uma vira um botão, e só a recomendada é
// cheia. "Resolver" não é link: avisa quem monta o diálogo das escolhas (`resolve`),
// um só por tela. O plano mora na Produção, que abre na janela dela
// (`useOperatorAppLink`).
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

const emit = defineEmits<{
  /** "Resolver" foi tocado: quem monta abre o diálogo deste pedido. */
  resolve: [];
}>();

const { attrsFor } = useOperatorAppLink();
const buttons = computed(() =>
  exitButtons(props.exits, props.tone).map((button) => ({
    ...button,
    link: button.external ? attrsFor(button.href) : null,
  })),
);
</script>

<template>
  <template v-for="button in buttons" :key="button.ref">
    <NuxtButton
      v-if="button.opensDialog"
      type="button"
      :disabled="button.disabled"
      :icon="button.disabled ? 'i-lucide-lock' : button.icon"
      :label="button.label"
      :color="button.color"
      :variant="button.variant"
      class="max-sm:justify-center"
      :aria-label="`${button.label}: pedido ${code}`"
      :data-promise-exit="button.ref"
      @click="emit('resolve')"
    />
    <NuxtButton
      v-else
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
</template>
