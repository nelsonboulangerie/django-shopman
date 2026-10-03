<script setup lang="ts">
// Celular (abaixo de md): alertas e avisos na barra de 56px do cabeçalho de cada tela,
// como na prévia v3 (`orders-phone3.html`). Do tablet para cima eles moram no pé do
// rail (`GestorNav`). Montados por JS, não só escondidos por CSS: dois sinos no DOM
// seriam dois "Alertas" para quem procura pelo nome.
const isPhone = useMediaQuery("(max-width: 767.98px)");
</script>

<template>
  <template v-if="isPhone">
    <AlertsBell />
    <NotificationBell />
  </template>
</template>
