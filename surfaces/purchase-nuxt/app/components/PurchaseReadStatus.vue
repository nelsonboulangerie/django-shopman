<script setup lang="ts">
// O selo de leitura de toda tela do Compras, no `#status` do cabeçalho: "Lido às 10:42",
// "Lendo" ou "Sem leitura". A hora mora em `useState("purchase-read-at")`, escrita
// pelo `app.vue` a cada leitura que deu certo. Tom `calm`, nunca `live`: o Compras não
// tem SSE, lê ao abrir e em Atualizar (o mesmo do selo do chão, `usePurchaseReadSeal`).
// Abaixo de `lg` ele sai: a leitura mora no selo do trocador (`seal-tone`).
const { pending, readonlyFallback, backendBlockTitle } = usePurchaseDesk();
const readAt = useState("purchase-read-at", () => "");
const tone = computed(() => (readonlyFallback.value ? "off" : "calm"));
const label = computed(() =>
  readonlyFallback.value ? "Sem leitura" : pending.value ? "Lendo" : readAt.value ? `Lido às ${readAt.value}` : "Lido",
);
</script>

<template>
  <OperatorLiveStatus
    :tone="tone"
    :time="readAt"
    :label="label"
    :short-label="pending || !readAt ? '' : readAt"
    :detail="readonlyFallback ? backendBlockTitle : 'Última leitura da base de compras. Atualizar lê de novo.'"
  />
</template>
