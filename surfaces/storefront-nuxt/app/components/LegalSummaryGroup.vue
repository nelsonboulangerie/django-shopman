<script setup lang="ts">
// Um grupo do resumo. Em `essentials` é um bloco com o título do grupo (uma pergunta ou um tema); em
// `list` a pergunta some e os itens entram na lista corrida do card.
import { legalSummaryVariantKey } from '~/presentation/legal'

defineProps<{ title: string }>()
const variant = inject(legalSummaryVariantKey, computed(() => 'list' as const))
</script>

<template>
  <div v-if="variant === 'essentials'" class="rounded-lg border bg-card p-4" data-legal-summary-group>
    <h3 class="font-semibold leading-snug">{{ title }}</h3>
    <ul class="mt-2 shop-stack-tight">
      <slot />
    </ul>
  </div>
  <ul v-else class="shop-stack-tight" data-legal-summary-group>
    <slot />
  </ul>
</template>
