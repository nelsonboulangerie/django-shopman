<script setup lang="ts">
// A casa do Marketing é a fila de decisões (decisão do dono, 03/10/2026). Os ajustes
// moram em `/settings/campaigns`, `/settings/templates`, `/settings/offers` e `/settings/platforms`.
useHead({ title: "Decisões" });
</script>

<template>
  <MarketingDecisionQueue />
</template>
