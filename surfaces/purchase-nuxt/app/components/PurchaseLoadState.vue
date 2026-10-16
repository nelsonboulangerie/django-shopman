<script setup lang="ts">
// O estado da tela do Compras (`OperatorScreenState`, uma frase por estado): a base
// carregando pela primeira vez, ou a leitura que não veio. Com a base na mão, mostra a
// tela (slot padrão). As quatro seções leem o mesmo carregamento.
const { pending, backendReady, readonlyFallback, backendBlockMessage, refresh } = usePurchaseDesk();
</script>

<template>
  <OperatorScreenState
    v-if="readonlyFallback"
    state="error"
    what="as compras"
    :description="backendBlockMessage"
    data-purchase-load-error
    @retry="refresh()"
  />
  <OperatorScreenState v-else-if="pending && !backendReady" state="loading" what="as compras" />
  <slot v-else />
</template>
