<script setup lang="ts">
// O estado da tela, um só na suíte (WP-FASE2-UX-OPERADOR, K7): carregando, vazio, erro e
// sem conexão, com UMA redação por estado (`presentation/screenState.ts`).
//
// - Carregando e vazio são o `NuxtEmpty` oficial (o carregando com `loading`).
// - Erro é o `NuxtAlert` `subtle` `error`, com "Tentar de novo" na cor do aviso (a
//   exceção declarada do conjunto mínimo: a saída do aviso repete a cor dele), botão
//   `md` como o resto da suíte, nunca o `xs` do default do aviso.
// - Sem conexão é o `NuxtAlert` `warning`, com a hora da leitura que está na tela.
// - `in-card`: dentro de um cartão o `NuxtEmpty` perde a moldura própria (`naked`); no
//   corpo da página, fica com ela. Uma regra, em vez de cada tela escolher.
//
// O erro e o sem conexão ficam no lugar do conteúdo que não veio. Aviso que vale para a
// tela inteira mora no `alerts` do `OperatorPageHeader`; sem rede no app inteiro, no
// `OfflineBanner`.
import { computed } from "vue";

import {
  SCREEN_STATE_RETRY_LABEL,
  screenStateCopy,
  type OperatorScreenStateKind,
} from "../presentation/screenState";

const props = withDefaults(
  defineProps<{
    state: OperatorScreenStateKind;
    /** O que a tela mostra, com artigo: "a fila", "os lotes do período". */
    what?: string;
    /** Título próprio (o vazio quase sempre tem: "Nenhum lote fechado no período"). */
    title?: string;
    description?: string;
    /** Ícone do vazio. */
    icon?: string;
    /** Hora da leitura que está na tela, para o sem conexão ("10:42"). */
    since?: string;
    /** Dentro de um cartão: sem a moldura própria do vazio e do carregando. */
    inCard?: boolean;
  }>(),
  {
    what: "",
    title: "",
    description: "",
    icon: "i-lucide-inbox",
    since: "",
    inCard: false,
  },
);

const emit = defineEmits<{ retry: [] }>();

const copy = computed(() => screenStateCopy(props.state, { what: props.what, since: props.since }));
const title = computed(() => props.title || copy.value.title);
const description = computed(() => props.description || copy.value.description);
const variant = computed(() => (props.inCard ? "naked" : "outline"));

const retryActions = computed(() => [
  {
    label: SCREEN_STATE_RETRY_LABEL,
    icon: "i-lucide-refresh-cw",
    color: "error" as const,
    variant: "outline" as const,
    size: "md" as const,
    onClick: () => emit("retry"),
  },
]);
</script>

<template>
  <NuxtEmpty
    v-if="state === 'loading'"
    loading
    :variant="variant"
    :title="title"
    :description="description || undefined"
    data-operator-screen-state="loading"
  />
  <NuxtEmpty
    v-else-if="state === 'empty'"
    :variant="variant"
    :icon="icon"
    :title="title"
    :description="description || undefined"
    data-operator-screen-state="empty"
  >
    <template v-if="$slots.actions" #actions><slot name="actions" /></template>
  </NuxtEmpty>
  <NuxtAlert
    v-else-if="state === 'error'"
    color="error"
    variant="subtle"
    icon="i-lucide-circle-alert"
    orientation="horizontal"
    :title="title"
    :description="description || undefined"
    :actions="retryActions"
    role="alert"
    data-operator-screen-state="error"
  />
  <NuxtAlert
    v-else
    color="warning"
    variant="subtle"
    icon="i-lucide-wifi-off"
    :title="title"
    :description="description || undefined"
    role="status"
    data-operator-screen-state="offline"
  />
</template>
