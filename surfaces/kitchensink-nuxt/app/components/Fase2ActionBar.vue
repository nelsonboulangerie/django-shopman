<script setup lang="ts">
// Protótipo da `OperatorActionBar` (K3 do WP-FASE2-UX-OPERADOR): a estrutura de
// sucesso do Storefront (`.shop-action-dock`) trazida como REGRA, não como classe.
// Uma ação principal, de largura inteira, com a linha de contexto acima (o número que
// a ação mexe) e o motivo escrito quando ela não pode. No kit ela mora no `#footer`
// do `OperatorSuiteShell`, EM FLUXO entre o conteúdo e a barra inferior (nunca
// `position: fixed`), marca `data-focus-obstruction` e some com o teclado aberto.
withDefaults(
  defineProps<{
    contextLabel: string;
    contextValue: string;
    action: string;
    reason?: string;
    loading?: boolean;
    secondary?: string;
  }>(),
  { reason: "", loading: false, secondary: "" },
);
defineEmits<{ act: []; secondary: [] }>();
</script>

<template>
  <div class="space-y-2 border-t border-default bg-default p-3" data-focus-obstruction data-fase2-action-bar>
    <div class="flex items-baseline justify-between gap-3">
      <span class="text-xs text-muted">{{ contextLabel }}</span>
      <span class="text-base font-semibold tabular-nums">{{ contextValue }}</span>
    </div>
    <div class="flex items-center gap-2">
      <NuxtButton
        v-if="secondary"
        :label="secondary"
        color="neutral"
        variant="ghost"
        size="xl"
        @click="$emit('secondary')"
      />
      <NuxtButton
        :label="action"
        size="xl"
        block
        :loading="loading"
        :disabled="Boolean(reason)"
        @click="$emit('act')"
      />
    </div>
    <p v-if="reason" class="text-xs text-muted" role="status">{{ reason }}</p>
  </div>
</template>
