<script setup lang="ts">
// A casa do Marketing é a fila de decisões (decisão do dono, 03/10/2026). O
// panorama antigo continua em `/v2?area=today`, e as áreas de ajuste em `/v2`.
useHead({ title: "Decisões" });
</script>

<template>
  <MarketingDecisionQueue />
</template>
