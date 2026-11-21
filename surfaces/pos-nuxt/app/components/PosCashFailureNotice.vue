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
  /**
   * O botão que resolve, dentro do aviso (regra do dono, 20/11): o aviso diz o que
   * fazer e já traz o gesto na mão, em vez de mandar procurar o botão do diálogo.
   */
  actionLabel?: string;
  /** O gesto está em voo: o botão do aviso espera junto com o do diálogo. */
  busy?: boolean;
}>();

const emit = defineEmits<{ dismiss: []; action: [] }>();

const visible = computed(() => props.failure?.gesture === props.gesture);

// O FOCO vai para o botão que resolve. O botão que disparou o gesto fica desabilitado
// enquanto ele corre, e o navegador joga o foco no `body` quando o elemento focado
// se desabilita: depois da falha, o teclado (e o leitor de tela) perdia o lugar
// fora do diálogo (prévia do #2726). Cada falha nova traz o foco de volta.
const root = useTemplateRef<{ $el?: HTMLElement }>("root");
watch(
  () => (visible.value ? props.failure : null),
  async (failure) => {
    if (!failure) return;
    await nextTick();
    const el = root.value?.$el;
    if (!(el instanceof HTMLElement)) return;
    const action = el.querySelector<HTMLButtonElement>('[data-slot="actions"] button:not([aria-label])');
    if (action) action.focus();
    else el.focus();
  },
);
</script>

<template>
  <NuxtAlert
    v-if="visible"
    ref="root"
    tabindex="-1"
    color="error"
    variant="subtle"
    icon="i-lucide-circle-alert"
    :title="props.failure?.message"
    :actions="alertActions('error', [props.actionLabel ? {
      label: props.actionLabel,
      icon: 'i-lucide-rotate-ccw',
      disabled: props.busy,
      loading: props.busy,
      onClick: () => emit('action'),
    } : null])"
    orientation="vertical"
    v-bind="ALERT_CLOSE_PROPS"
    role="alert"
    class="w-full"
    data-cash-failure
    :data-cash-failure-gesture="props.gesture"
    @update:open="(open: boolean) => { if (!open) emit('dismiss'); }"
  />
</template>
