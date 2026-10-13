<script setup lang="ts">
// Histórico de hoje (dono, 13/10/2026): o que esta estação concluiu e o que caiu desde
// 0h. Mora no ⋯ da estação e no toque longo do celular, nunca num botão da grade. Cada
// linha diz o código, a encomenda e o cliente quando é encomenda, os itens, a trilha
// (recebido, iniciado, Pronto ou Cancelado, com quem) e o tempo de preparo. Tocar na
// linha abre o pedido em só leitura; Reabrir só onde a régua do servidor deixa, e onde
// não deixa a linha diz por quê (refazer nasce no PDV ou no Gestor).
import type { KDSHistoryEntryProjection, KDSHistoryProjection } from "~/types/kds";
import { historyEmptyTitle, historyFootnote, historyRow } from "~/presentation/history";

const props = withDefaults(
  defineProps<{
    open: boolean;
    history: KDSHistoryProjection | null;
    query: string;
    pending?: boolean;
    error?: unknown;
    /** O ticket que está voltando à fila agora (o Reabrir espera). */
    reopeningPk?: number | null;
  }>(),
  { pending: false, error: undefined, reopeningPk: null },
);
const emit = defineEmits<{
  "update:open": [boolean];
  "update:query": [string];
  view: [KDSHistoryEntryProjection];
  reopen: [number];
  retry: [];
}>();

const rows = computed(() =>
  (props.history?.entries ?? []).map((entry) => ({ entry, row: historyRow(entry) })),
);
const footnote = computed(() => (props.history ? historyFootnote(props.history) : ""));
const queryModel = computed({
  get: () => props.query,
  set: (value: string) => emit("update:query", String(value ?? "")),
});
</script>

<template>
  <NuxtModal
    :open="open"
    title="Histórico de hoje"
    description="Concluídos e cancelados nesta estação desde 0h."
    :ui="{ content: 'sm:max-w-2xl', body: 'flex flex-col gap-3' }"
    data-kds-history
    @update:open="emit('update:open', Boolean($event))"
  >
    <template #body>
      <NuxtInput
        v-model="queryModel"
        type="search"
        icon="i-lucide-search"
        placeholder="Buscar pelo código"
        aria-label="Buscar no histórico de hoje pelo código do pedido"
        class="w-full"
        data-kds-history-search
      />

      <OperatorScreenState
        v-if="!history && pending"
        state="loading"
        in-card
        what="o histórico de hoje"
      />
      <OperatorScreenState
        v-else-if="!history && error"
        state="error"
        in-card
        what="o histórico de hoje"
        @retry="emit('retry')"
      />
      <OperatorScreenState
        v-else-if="history && !rows.length"
        state="empty"
        in-card
        icon="i-lucide-history"
        :title="historyEmptyTitle(query)"
      />

      <!-- Lista (exceção declarada ao conteúdo centrado): uma linha por pedido, a mais
           recente primeiro, separadas por fio, sem cartão dentro do diálogo. -->
      <ul v-else-if="rows.length" class="flex flex-col divide-y divide-default" data-kds-history-list>
        <li
          v-for="{ entry, row } in rows"
          :key="row.pk"
          class="flex items-start gap-3 py-2.5"
          :data-kds-history-row="row.pk"
        >
          <button
            type="button"
            class="min-w-0 flex-1 rounded-md text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            :aria-label="`Ver o pedido ${row.code}`"
            data-kds-history-view
            @click="emit('view', entry)"
          >
            <span class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span class="text-lg font-bold leading-tight tabular-nums">{{ row.code }}</span>
              <NuxtBadge v-if="row.cancelled" color="error" variant="soft" label="Cancelado" />
              <span v-if="row.overline" class="op-label font-semibold">{{ row.overline }}</span>
              <span v-if="row.prep" class="ms-auto op-label tabular-nums text-muted-foreground">{{ row.prep }}</span>
            </span>
            <span class="block break-words op-body">{{ row.items }}</span>
            <span class="block break-words op-label text-muted-foreground" data-kds-history-trail>{{ row.trail }}</span>
            <span
              v-for="(line, i) in row.undone"
              :key="i"
              class="flex items-start gap-1 op-label text-warning"
              data-kds-history-undone
            >
              <Icon name="lucide:undo-2" class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span class="min-w-0 break-words">{{ line }}</span>
            </span>
            <span
              v-if="row.blockedReason"
              class="flex items-start gap-1 op-label text-muted-foreground"
              data-kds-history-blocked
            >
              <Icon name="lucide:lock" class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span class="min-w-0 break-words">{{ row.blockedReason }}</span>
            </span>
          </button>
          <NuxtButton
            v-if="row.canReopen"
            color="neutral"
            variant="outline"
            icon="i-lucide-rotate-ccw"
            label="Reabrir"
            class="shrink-0"
            :loading="reopeningPk === row.pk"
            :disabled="reopeningPk != null && reopeningPk !== row.pk"
            :aria-label="`Reabrir o pedido ${row.code}: volta para a fila em preparo`"
            data-kds-history-reopen
            @click="emit('reopen', row.pk)"
          />
        </li>
      </ul>

      <p v-if="footnote" class="op-micro text-muted-foreground" data-kds-history-footnote>{{ footnote }}</p>
    </template>
  </NuxtModal>
</template>
