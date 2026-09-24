<script setup lang="ts">
// "Em poucas palavras": o resumo do documento legal, no topo.
//
// ⚠️ O RESUMO É TEXTO DO DOCUMENTO. Ele mora no template da página, e a trava
// de versão (tests/legalVersion.test.ts) o confere junto com o resto: mudar
// uma palavra aqui pede versão nova em `shopman/storefront/presentation/legal.py`.
// E ele não pode dizer nada que o texto completo não diga. Cada item aponta a
// seção que o sustenta (`to="#sharing"` vira "ver §4").
//
// Duas apresentações em prévia (PR draft, para o dono escolher):
//   - `list`       — card claro, um item por linha, com ícone;
//   - `essentials` — "O essencial": três blocos de pergunta e resposta.
// A escolhida fica, e a outra sai deste componente.
import { legalSummaryVariantKey, type LegalSummaryVariant } from '~/presentation/legal'

const props = withDefaults(defineProps<{ variant?: LegalSummaryVariant }>(), { variant: 'list' })
provide(legalSummaryVariantKey, computed(() => props.variant))
</script>

<template>
  <section
    aria-labelledby="legal-summary-title"
    class="mt-6"
    :class="variant === 'list' ? 'rounded-lg border bg-bottomnav p-4 sm:p-6' : ''"
    :data-legal-summary="variant"
  >
    <h2 id="legal-summary-title" class="shop-kicker">
      {{ variant === 'list' ? 'Em poucas palavras' : 'O essencial' }}
    </h2>
    <div
      class="mt-3"
      :class="variant === 'list' ? 'shop-stack-tight' : 'grid gap-3 sm:grid-cols-3'"
    >
      <slot />
    </div>
    <p class="mt-4 shop-meta" data-legal-summary-disclaimer>
      <slot name="disclaimer" />
    </p>
  </section>
</template>
