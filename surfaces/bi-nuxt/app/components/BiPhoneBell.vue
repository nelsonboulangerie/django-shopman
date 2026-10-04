<script setup lang="ts">
// Celular (abaixo de md): Avisos na barra de 56px do cabeçalho de cada tela, como no
// Gestor. Do tablet para cima o sino mora no pé do rail (`BiNav`). Montado por JS, não
// só escondido por CSS: dois sinos no DOM seriam dois "Avisos" para quem procura pelo nome.
const isPhone = useMediaQuery("(max-width: 767.98px)");
</script>

<template>
  <NotificationBell v-if="isPhone" />
</template>
