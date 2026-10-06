<script setup lang="ts">
// Casca do app: gate de operador + raiz Nuxt UI + outlet. A página compõe o
// shell canônico do catálogo sem manter uma segunda navegação local.
const OPERATOR_PERM = "backstage.view_operator_kitchen_sink";
const harness = useRuntimeConfig().public.kitchenSinkHarness === true;
const gate = harness
  ? {
      canIdentify: ref(true),
      sessionUnavailable: ref(false),
      refresh: async () => undefined,
      locked: ref(false),
      mustChange: ref(false),
    }
  : useOperatorLock(OPERATOR_PERM);
const { canIdentify, sessionUnavailable, refresh, locked, mustChange } = gate;

useOperatorWindowTitle();
</script>

<template>
  <OperatorAppRoot>
    <NuxtRouteAnnouncer />
    <OfflineBanner />
    <NuxtPage v-if="canIdentify || harness" />
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy
         subiria a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="!harness && sessionUnavailable" scope="o Catálogo do operador" @retry="refresh()" />
    <OperatorLogin v-if="!harness && !canIdentify && !sessionUnavailable" />
    <OperatorLock v-else-if="!harness && (locked || mustChange)" :perm="OPERATOR_PERM" />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </OperatorAppRoot>
</template>
