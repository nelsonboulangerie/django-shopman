<script setup lang="ts">
import { discountDisplay, promoSavingsNote } from '~/presentation/cart'
import type { CartProjection } from '~/types/shopman'

// O resumo fecha com as linhas (decisão do dono 1, 16/11/2026): o Subtotal é a
// soma das linhas como a tela as mostra, com a promoção do produto já abatida.
// A nota diz quanto as promoções economizaram, sem subtrair de novo; as linhas
// de desconto são só as do pedido (cupom, pontos).

defineProps<{
  cart: CartProjection
  compact?: boolean
  flat?: boolean
}>()
</script>

<template>
  <UiDescriptionList :class="[flat ? '' : 'rounded-lg border bg-card px-3', compact ? 'text-sm' : '']">
    <UiDescriptionListTerm>Subtotal</UiDescriptionListTerm>
    <UiDescriptionListDetails class="tabular-nums sm:text-right" data-summary-subtotal>
      {{ cart.lines_subtotal_display }}
      <span v-if="promoSavingsNote(cart)" class="block shop-meta" data-summary-promo-savings>{{ promoSavingsNote(cart) }}</span>
    </UiDescriptionListDetails>

    <template v-for="discount in cart.order_discount_lines" :key="discount.label">
      <UiDescriptionListTerm>{{ discount.label }}</UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums text-primary sm:text-right">
        {{ discountDisplay(discount.amount_display) }}
      </UiDescriptionListDetails>
    </template>

    <template v-if="cart.delivery_fee_display">
      <UiDescriptionListTerm>
        Entrega<span v-if="cart.delivery_distance_display" class="shop-muted font-normal"> · {{ cart.delivery_distance_display }}</span>
      </UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums sm:text-right">{{ cart.delivery_fee_display }}</UiDescriptionListDetails>
    </template>

    <UiDescriptionListTerm class="font-semibold text-foreground">Total</UiDescriptionListTerm>
    <UiDescriptionListDetails :class="[compact ? 'text-base' : 'text-xl', 'font-semibold tabular-nums sm:text-right']">
      {{ cart.grand_total_display }}
    </UiDescriptionListDetails>
  </UiDescriptionList>
</template>
