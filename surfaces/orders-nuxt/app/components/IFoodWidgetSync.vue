<script setup lang="ts">
// Mantém o botão do iFood em dia com a casa (DEV-2026-023): a cada evento do canal
// de pedidos (com poll calmo de reserva), relê se há pedido iFood em andamento, e
// mostra ou esconde o botão. Vive dentro da página liberada, para o SSE de pedidos
// só abrir com alguém identificado. Não desenha nada.
const ifoodWidget = useIFoodWidget();
useBackstageEvents("orders", () => void ifoodWidget.refresh(), {
  pollMs: 60_000,
});
watch(
  [ifoodWidget.visible, ifoodWidget.state],
  () => ifoodWidget.applyVisibility(),
  { immediate: true },
);
</script>

<template>
  <span hidden data-ifood-widget-sync />
</template>
