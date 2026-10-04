<script setup lang="ts">
// Celular (abaixo de md): o sino na barra de 56px do cabeçalho de cada tela, como na
// prévia v3 (`purchase-receive-phone3.html`). Do tablet para cima ele mora no pé do rail
// (`PurchaseNav`). Montado por JS, não só escondido por CSS: dois sinos no DOM seriam
// dois "Avisos" para quem procura pelo nome.
const isPhone = useMediaQuery("(max-width: 767.98px)");
</script>

<template>
  <NotificationBell v-if="isPhone" />
</template>
