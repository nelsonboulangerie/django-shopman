<script setup lang="ts">
// O histórico do salão: cada gravação, com quem, quando e o quê (antes e depois).
// Lido do registro que o servidor escreve a cada Salvar (`LogEntry` do Admin, o mesmo
// histórico que o Admin mostra na mesa). Só leitura.
import type { SeatingHistoryEntry } from "~/types/seating";

defineProps<{ open: boolean; entries: readonly SeatingHistoryEntry[] }>();
const emit = defineEmits<{ "update:open": [value: boolean] }>();
</script>

<template>
  <UiSheet :open="open" @update:open="(value) => emit('update:open', value)">
    <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-md" :title="undefined">
      <template #header>
        <div class="border-b border-border px-4 pt-4 pb-3">
          <UiSheetTitle class="op-title">Histórico do salão</UiSheetTitle>
          <UiSheetDescription class="op-micro text-muted-foreground">
            Quem mudou o quê, e quando. As últimas 30 mudanças.
          </UiSheetDescription>
        </div>
      </template>
      <template #content>
        <div class="min-h-0 flex-1 overflow-y-auto">
          <p v-if="!entries.length" class="p-4 op-body text-muted-foreground">Nenhuma mudança registrada ainda.</p>
          <ol v-else class="divide-y divide-border" data-seating-history>
            <li v-for="entry in entries" :key="entry.id" class="flex flex-col gap-1 px-4 py-3">
              <p class="op-body">{{ entry.summary }}</p>
              <p class="op-micro text-muted-foreground tabular-nums">{{ entry.who || "Admin" }} · {{ entry.at_label }}</p>
            </li>
          </ol>
        </div>
      </template>
    </UiSheetContent>
  </UiSheet>
</template>
