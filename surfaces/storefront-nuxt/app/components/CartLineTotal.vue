<script setup lang="ts">
import { lineTotal } from '~/presentation/cart'
import type { CartItemProjection } from '~/types/shopman'

// O total da linha, igual na sacola e no checkout (decisão do dono 1,
// 16/11/2026): com promoção do produto, o total com desconto e o cheio riscado;
// sem promoção, só o total. A palavra "antes" acompanha o risco, como no
// cardápio: risco mudo não diz a quem ouve a tela que o desconto já entrou.
const props = defineProps<{
  line: Pick<CartItemProjection, 'line_total_display' | 'line_total_struck_display'>
  // Empilhado: o cheio em cima e o total embaixo, alinhados à direita (linha da sacola).
  stacked?: boolean
}>()

const total = computed(() => lineTotal(props.line))
</script>

<template>
  <span
    :class="stacked ? 'flex flex-col items-end' : 'inline-flex flex-wrap items-baseline justify-end gap-x-1.5'"
    data-line-total
  >
    <span v-if="total.original" class="shop-meta" data-line-total-struck>antes <span class="line-through">{{ total.original }}</span></span>
    <span class="shop-price">{{ total.current }}</span>
  </span>
</template>
