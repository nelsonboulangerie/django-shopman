<script setup lang="ts">
// Shell do B.I. Casca fina: produção/vendas/caixa/clientes são páginas
// próprias (pages/), e o shell segura o outlet + a chrome + o gate de operador.
//
// Gate: `backstage.view_bi` — leitura analítica cross-suite é persona de
// gestão (ADR-021 §5), não de quem opera o turno.
const OPERATOR_PERM = "backstage.view_bi";
const { authenticated, locked, mustChange, operator, lock } = useOperatorLock(OPERATOR_PERM);

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useHead({ title: "B.I." });
</script>

<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit) — global, só aparece offline. -->
    <OfflineBanner />
    <div v-if="authenticated" class="sticky top-0 flex h-screen shrink-0 print:hidden">
      <OperatorRail
        app-icon="chart-line"
        app-label="B.I."
        :central-url="hubUrl"
        :operator-name="operator?.name"
        @lock="lock"
      />
    </div>
    <div class="flex min-w-0 flex-1 flex-col">
      <BiTopBar v-if="authenticated" />
      <NuxtPage />
    </div>
    <OperatorLogin v-if="!authenticated" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <UiSonner />
  </div>
</template>
