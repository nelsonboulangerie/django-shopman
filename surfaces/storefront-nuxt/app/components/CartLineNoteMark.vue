<script setup lang="ts">
// Marca do item que leva observação: selo + uma linha com o texto. A MESMA
// marcação na sacola e na revisão da finalização, no molde dos outros selos da
// linha (Preparado na hora, Lista de espera): o cliente reconhece de relance o
// item que vai com pedido especial, nos dois lugares em que confere a sacola.
defineProps<{
  notes: string
}>()
</script>

<template>
  <div class="min-w-0" data-cart-line-note-mark>
    <UiBadge variant="outline">
      <Icon name="lucide:message-square-text" class="mr-1 size-3.5" />
      Com observação
    </UiBadge>
    <p class="mt-1 truncate shop-meta text-foreground" :title="notes" data-cart-line-note-text>{{ notes }}</p>
  </div>
</template>
