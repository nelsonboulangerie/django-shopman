<script setup lang="ts">
// Aviso do pedido de teste da homologação do iFood. Um desenho só para os dois
// cards: a caixa âmbar DENTRO da moldura, antes do código — quem lê o card tem
// de saber que aquilo não se forna nem se entrega antes de ler o que é. O que
// muda entre as telas é só o verbo que o aviso proíbe.
defineProps<{ label: string; forbids: string }>();
</script>

<template>
  <p
    class="flex items-center gap-1.5 rounded-md border border-warning/40 bg-warning/20 px-2 py-1.5 text-sm font-bold uppercase tracking-wide"
    data-kds-test-order
  >
    <Icon name="lucide:flask-conical" class="size-4 shrink-0" />
    {{ label }} · {{ forbids }}
  </p>
</template>
