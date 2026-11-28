<script setup lang="ts">
import { computed } from "vue";
const props = withDefaults(
  defineProps<{
    count: number;
    pending: boolean;
    placement?: "toolbar" | "base";
    undo?: { until: string; serverNow: string; count?: number } | null;
  }>(),
  { placement: "toolbar", undo: null },
);
const emit = defineEmits<{
  clear: [];
  archive: [active: boolean];
  undo: [];
  expire: [];
}>();
const items = computed(() => [
  [
    {
      label: "Arquivar",
      icon: "i-lucide-archive",
      disabled: props.pending || props.count === 0,
      onSelect: () => emit("archive", false),
    },
    {
      label: "Desarquivar",
      icon: "i-lucide-archive-restore",
      disabled: props.pending || props.count === 0,
      onSelect: () => emit("archive", true),
    },
  ],
]);
</script>
<template>
  <OperatorBulkBar
    :count="count"
    :empty="
      undo
        ? `${undo.count || 0} ${undo.count === 1 ? 'fornecedor alterado' : 'fornecedores alterados'}`
        : 'Marque fornecedores'
    "
    scope="Fornecedores"
    :items="items"
    :placement="placement"
    @clear="emit('clear')"
  >
    <template v-if="undo" #lead>
      <OperatorTimedButton
        label="Desfazer"
        icon="i-lucide-undo-2"
        color="neutral"
        variant="outline"
        :until="undo.until"
        :server-now="undo.serverNow"
        :duration="15000"
        :loading="pending"
        @click="emit('undo')"
        @expire="emit('expire')"
      />
    </template>
  </OperatorBulkBar>
</template>
