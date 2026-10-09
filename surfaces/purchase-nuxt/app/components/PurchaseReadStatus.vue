<script setup lang="ts">
// O selo de leitura de toda tela do Compras, no `#status` do cabeçalho: "Lido 10:42",
// "Lendo" ou "Sem leitura". A hora mora em `useState("purchase-read-at")`, escrita
// pelo `app.vue` a cada leitura que deu certo.
const { pending, readonlyFallback, backendBlockTitle } = usePurchaseDesk();
const readAt = useState("purchase-read-at", () => "");
const tone = computed(() => (readonlyFallback.value ? "off" : pending.value ? "calm" : "live"));
const label = computed(() => (readonlyFallback.value ? "Sem leitura" : pending.value ? "Lendo" : "Lido"));
</script>

<template>
  <OperatorLiveStatus
    :tone="tone"
    :time="readAt"
    :label="label"
    :detail="readonlyFallback ? backendBlockTitle : 'Última leitura da base de compras. Atualizar lê de novo.'"
  />
</template>
