<script setup lang="ts">
// Um item do resumo: uma frase curta e a seção que a sustenta ("ver §4").
// O número vem da ordem real das seções (`LegalDocument`), nunca digitado.
import { legalGoToKey, legalSectionNumberKey, legalSummaryVariantKey } from '~/presentation/legal'

const props = defineProps<{ to: string, icon: string }>()
const variant = inject(legalSummaryVariantKey, computed(() => 'list' as const))
const numberOf = inject(legalSectionNumberKey, () => null)
const goTo = inject(legalGoToKey, () => {})
const anchor = computed(() => props.to.replace(/^#/, ''))
</script>

<template>
  <li class="flex gap-3 text-sm leading-6" :data-legal-summary-item="anchor">
    <Icon v-if="variant === 'list'" :name="icon" class="mt-1 size-4 shrink-0 text-primary" aria-hidden="true" />
    <span>
      <slot />
      <a
        v-if="numberOf(anchor)"
        :href="`#${anchor}`"
        class="whitespace-nowrap text-muted-foreground underline underline-offset-2 hover:text-foreground"
        data-legal-summary-ref
        @click.prevent="goTo(anchor)"
      >ver §{{ numberOf(anchor) }}</a>
    </span>
  </li>
</template>
