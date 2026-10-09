<script setup lang="ts">
// O detalhe do pedido aberto a partir de uma lista (rodada 2). Anterior e próximo andam
// DENTRO do recorte de onde a pessoa veio, e o recorte aparece escrito sob o título
// ("em iFood atrasados"): o "3 de 24" só faz sentido com ele.
// Na mesa ele DIVIDE a tela com a lista (a lista encolhe e solta colunas de apoio);
// no celular ele é a tela inteira. Nunca cobre a lista na mesa.
import { brl } from "../data/fase2";
import type { Fase2Order } from "../types/fase2";

defineProps<{ order: Fase2Order; index: number; total: number; context: string }>();
const emit = defineEmits<{ go: [index: number]; close: [] }>();
</script>

<template>
  <div class="flex h-full flex-col" data-fase2-detail>
    <div class="flex flex-wrap items-center gap-2 border-b border-default px-3 py-2">
      <h2 class="text-lg font-semibold tabular-nums text-highlighted">Pedido {{ order.ref }}</h2>
      <NuxtBadge :label="order.stage" :color="order.stage === 'Cancelado' ? 'error' : 'neutral'" />
      <div class="ms-auto flex items-center gap-1">
        <Fase2RecordNav :index="index" :total="total" noun="Pedido" @go="emit('go', $event)" />
        <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar o pedido" @click="emit('close')" />
      </div>
      <p class="basis-full text-sm text-muted">em {{ context }}</p>
    </div>
    <div class="space-y-4 p-3 text-sm">
      <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <dt class="text-muted">Cliente</dt>
        <dd>{{ order.customer }}</dd>
        <dt class="text-muted">Quando</dt>
        <dd class="tabular-nums">{{ order.date }} às {{ order.eta }}</dd>
        <dt class="text-muted">Canal</dt>
        <dd>{{ order.channel }} · {{ order.payment }}</dd>
      </dl>
      <ul class="divide-y divide-default">
        <li v-for="item in order.items" :key="item" class="py-1.5">{{ item }}</li>
      </ul>
      <p class="flex justify-between font-semibold">
        <span>Total</span><span class="tabular-nums">{{ brl(order.total_q) }}</span>
      </p>
    </div>
  </div>
</template>
