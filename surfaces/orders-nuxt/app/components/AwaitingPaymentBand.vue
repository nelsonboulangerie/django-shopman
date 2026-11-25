<script setup lang="ts">
// Aguardando pagamento (DEV-2026-091, escolha do dono de 25/11/2026): o pedido novo
// que só espera o Pix ou o cartão cair. Não há o que fazer com ele ainda, então fica
// recolhido no fim (da Fila e da coluna Novos do Painel), sem som e fora da contagem.
// Quando o pagamento cai, o servidor dá a ele o `attention` e ele sobe tocando como
// pedido novo. Só leitura: o código abre o pedido.
import type { AwaitingPaymentRow } from "~/presentation/queue";

defineProps<{
  rows: AwaitingPaymentRow[];
  canOpen: boolean;
}>();
</script>

<template>
  <NuxtCollapsible
    v-if="rows.length"
    class="rounded-lg border border-dashed border-default"
    data-queue-awaiting-payment
  >
    <NuxtButton
      :label="`Aguardando pagamento (${rows.length})`"
      icon="i-lucide-hourglass"
      trailing-icon="i-lucide-chevron-down"
      color="neutral"
      variant="ghost"
      block
      class="min-h-11 justify-start"
      data-queue-awaiting-payment-toggle
    />
    <template #content>
      <ul class="flex flex-col gap-2 px-3 pb-3" data-queue-awaiting-payment-list>
        <li
          v-for="row in rows"
          :key="row.ref"
          class="flex flex-wrap items-baseline gap-x-3 gap-y-1"
          :data-queue-awaiting-payment-row="row.ref"
        >
          <NuxtLink
            v-if="canOpen"
            :to="`/${row.ref}`"
            class="op-figure leading-none hover:underline"
            :aria-label="`Abrir pedido ${row.ref}`"
            >{{ row.code }}</NuxtLink
          >
          <span v-else class="op-figure leading-none">{{ row.code }}</span>
          <span class="min-w-0 text-sm">{{ row.who }}</span>
          <span class="w-full text-xs text-muted sm:ms-auto sm:w-auto">{{ row.wait }}</span>
        </li>
      </ul>
    </template>
  </NuxtCollapsible>
</template>
