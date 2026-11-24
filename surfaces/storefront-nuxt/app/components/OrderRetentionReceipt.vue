<script setup lang="ts">
// O recibo do valor retido (#3538). Encomenda paga e não retirada: o que a loja
// reteve é multa, com recibo e sem nota fiscal (contador, 24/11/2026). O aviso ao
// cliente aponta para esta página, e o papel do balcão leva o QR para cá: os dois
// leem o mesmo registro. Só aparece quando a loja ficou com dinheiro; o texto vem
// pronto do servidor.
import type { RetentionReceipt } from '~/types/shopman'

defineProps<{ receipt: RetentionReceipt }>()
</script>

<template>
  <UiCard id="recibo" class="py-3" data-order-retention-receipt>
    <UiCardContent class="shop-stack-tight px-4 py-0">
      <div class="flex items-center gap-2">
        <Icon name="lucide:receipt" class="size-4 shrink-0 text-muted-foreground" />
        <p class="shop-item-title font-semibold text-foreground">{{ receipt.title }}</p>
      </div>
      <p
        v-for="line in receipt.issuer_lines"
        :key="line"
        class="shop-meta"
        data-retention-receipt-issuer
      >
        {{ line }}
      </p>
      <p class="shop-meta">
        {{ receipt.order_line }}<template v-if="receipt.commitment_display"> · {{ receipt.commitment_display }}</template>
      </p>
      <p v-if="receipt.closed_display" class="shop-meta">{{ receipt.closed_display }}</p>

      <ul v-if="receipt.lines.length" class="space-y-1 border-t pt-2" data-retention-receipt-lines>
        <li v-for="(line, index) in receipt.lines" :key="index" class="flex items-start justify-between gap-3 text-sm">
          <span class="min-w-0 break-words">
            {{ line.name }}
            <span class="block shop-meta">{{ line.qty_display }}</span>
          </span>
          <span class="shrink-0 shop-price">{{ line.value_display }}</span>
        </li>
      </ul>

      <dl class="space-y-1 border-t pt-2 text-sm" data-retention-receipt-money>
        <div v-for="row in receipt.money_rows" :key="row.label" class="flex justify-between gap-3">
          <dt class="text-muted-foreground">{{ row.label }}</dt>
          <dd class="shop-price">{{ row.value_display }}</dd>
        </div>
        <div class="flex justify-between gap-3 font-semibold text-foreground" data-retention-receipt-retained>
          <dt>{{ receipt.retained_label }}</dt>
          <dd class="shop-price">{{ receipt.retained_display }}</dd>
        </div>
      </dl>

      <p class="shop-meta" data-retention-receipt-nature>{{ receipt.nature }}</p>
      <p class="shop-meta" data-retention-receipt-not-fiscal>{{ receipt.not_fiscal }}</p>
    </UiCardContent>
  </UiCard>
</template>
