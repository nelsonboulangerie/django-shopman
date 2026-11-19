<script setup lang="ts">
// O erro de um gesto de caixa DENTRO do diálogo em que o gesto mora.
//
// O toast do erro nascia atrás do véu do diálogo aberto ("Saída de caixa"), com o
// texto apagado pela camada de cima, e era o único aviso que importava naquele
// momento (auditoria da prévia do WP-E6). Aqui ele fica junto do botão que repete o
// gesto. Regra da casa para aviso de tela: tem X, e volta enquanto a causa durar
// (a próxima falha do mesmo gesto acende de novo); some quando a repetição confirma.
import type { CashFailure, CashGesture } from "~/composables/usePosCashSession";

import { ALERT_CLOSE_PROPS } from "../../../operator-kit/app/composables/useAlertDismissals";

const props = defineProps<{
  failure: CashFailure | null;
  /** O gesto deste diálogo: o aviso só aparece para a falha dele. */
  gesture: CashGesture;
}>();

const emit = defineEmits<{ dismiss: [] }>();

const visible = computed(() => props.failure?.gesture === props.gesture);
</script>

<template>
  <NuxtAlert
    v-if="visible"
    color="error"
    variant="subtle"
    icon="i-lucide-circle-alert"
    :title="props.failure?.message"
    v-bind="ALERT_CLOSE_PROPS"
    role="alert"
    class="w-full"
    data-cash-failure
    :data-cash-failure-gesture="props.gesture"
    @update:open="(open: boolean) => { if (!open) emit('dismiss'); }"
  />
</template>
