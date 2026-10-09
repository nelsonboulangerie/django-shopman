<script setup lang="ts">
// O cartão de pedido da fila, rodada 2 (dono, 09/10: "cards sem destaque de cabeçalho
// e rodapé, salvo quando de fato necessários; arranjos compactos, econômicos e
// diretos"). Um bloco só: a linha do pedido (marcar, número, hora), o cliente (quebra,
// nunca corta) e os selos que mudam a decisão. Marcado = anel da cor da ação.
import { brl } from "../data/fase2";
import type { Fase2Order } from "../types/fase2";

const props = defineProps<{ order: Fase2Order }>();
const selected = defineModel<boolean>("selected", { default: false });
</script>

<template>
  <NuxtCard
    :ui="{ body: 'p-3 sm:p-3 space-y-1' }"
    :class="selected ? 'ring-2 ring-primary' : ''"
    :data-fase2-order="props.order.ref"
  >
    <div class="flex items-center gap-2">
      <NuxtCheckbox v-model="selected" :aria-label="`Selecionar o pedido ${order.ref}`" />
      <span class="font-semibold tabular-nums text-highlighted">{{ order.ref }}</span>
      <NuxtBadge v-if="order.stage === 'Atrasado'" color="error" label="Atrasado" />
      <span class="ms-auto text-sm tabular-nums text-muted">{{ order.eta }}</span>
    </div>
    <p class="text-sm text-default">{{ order.customer }}</p>
    <div class="flex flex-wrap items-center gap-1.5 text-sm text-muted">
      <NuxtBadge color="neutral" :label="order.channel" />
      <NuxtBadge v-if="order.payment" color="neutral" :label="order.payment" />
      <span class="ms-auto tabular-nums">{{ brl(order.total_q) }}</span>
    </div>
  </NuxtCard>
</template>
