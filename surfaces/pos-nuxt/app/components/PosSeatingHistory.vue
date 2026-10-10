<script setup lang="ts">
// O histórico do salão: cada gravação, com quem, quando e o quê (antes e depois).
// Lido do registro que o servidor escreve a cada Salvar (`LogEntry` do Admin, o mesmo
// histórico que o Admin mostra na mesa). Só leitura.
import type { SeatingHistoryEntry } from "~/types/seating";

defineProps<{ open: boolean; entries: readonly SeatingHistoryEntry[] }>();
const emit = defineEmits<{ "update:open": [value: boolean] }>();
</script>

<template>
  <NuxtSlideover
    :open="open"
    title="Histórico do salão"
    description="Quem mudou o quê, e quando. As últimas 30 mudanças."
    :ui="{ body: 'p-0 sm:p-0' }"
    data-seating-history-sheet
    @update:open="(value) => emit('update:open', value)"
  >
    <template #body>
      <OperatorScreenState
        v-if="!entries.length"
        state="empty"
        icon="i-lucide-history"
        title="Nenhuma mudança registrada ainda."
        in-card
      />
      <ol v-else class="divide-y divide-border" data-seating-history>
        <li v-for="entry in entries" :key="entry.id" class="flex flex-col gap-1 px-4 py-3">
          <p class="op-body">{{ entry.summary }}</p>
          <p class="op-micro text-muted-foreground tabular-nums">{{ entry.who || "Admin" }} · {{ entry.at_label }}</p>
        </li>
      </ol>
    </template>
  </NuxtSlideover>
</template>
