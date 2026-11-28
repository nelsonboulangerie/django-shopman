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
    <UiDescriptionListDetails class="tabular-nums sm:text-right" data-summary-subtotal data-decisive="price">
      {{ cart.lines_subtotal_display }}
    </UiDescriptionListDetails>
    <!-- A nota ocupa a largura inteira do resumo, logo abaixo do Subtotal: presa à
         coluna do valor, quebrava em duas linhas no computador. -->
    <dd v-if="promoSavingsNote(cart)" class="col-span-full -mt-2 pb-3 shop-meta sm:text-right" data-summary-promo-savings data-decisive="price">
      {{ promoSavingsNote(cart) }}
    </dd>

    <template v-for="discount in cart.order_discount_lines" :key="discount.label">
      <UiDescriptionListTerm>{{ discount.label }}</UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums text-promotion sm:text-right" data-decisive="price">
        {{ discountDisplay(discount.amount_display) }}
      </UiDescriptionListDetails>
    </template>

    <template v-if="cart.delivery_fee_display">
      <UiDescriptionListTerm>
        Entrega<span v-if="cart.delivery_distance_display" class="shop-muted font-normal"> · {{ cart.delivery_distance_display }}</span>
      </UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums sm:text-right" data-decisive="price">{{ cart.delivery_fee_display }}</UiDescriptionListDetails>
    </template>

    <UiDescriptionListTerm class="font-semibold text-foreground">Total</UiDescriptionListTerm>
    <UiDescriptionListDetails :class="[compact ? 'text-base' : 'text-xl', 'font-semibold tabular-nums sm:text-right']" data-decisive="total">
      {{ cart.grand_total_display }}
    </UiDescriptionListDetails>
  </UiDescriptionList>
</template>
