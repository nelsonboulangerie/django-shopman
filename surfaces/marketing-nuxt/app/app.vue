<script setup lang="ts">
// Shell do Marketing. Casca fina: painel, regras e histórico são páginas
// próprias (pages/), e o shell segura o outlet + a chrome + o gate de operador.
//
// Gate: `shop.manage_campaigns` — publicar em nome da marca é decisão de
// marketing, não de quem opera a fila de pedidos.
const OPERATOR_PERM = "shop.manage_campaigns";
const { authenticated, locked, mustChange, operator, lock } = useOperatorLock(OPERATOR_PERM);

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useHead({ title: "Marketing" });
</script>

<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit) — global, só aparece offline. -->
    <OfflineBanner />
    <div v-if="authenticated" class="sticky top-0 flex h-screen shrink-0 print:hidden">
      <OperatorRail
        app-icon="megaphone"
        app-label="Marketing"
        :central-url="hubUrl"
        :operator-name="operator?.name"
        @lock="lock"
      />
    </div>
    <div class="flex min-w-0 flex-1 flex-col">
      <CampaignTopBar v-if="authenticated" />
      <NuxtPage />
    </div>
    <OperatorLogin v-if="!authenticated" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <UiSonner />
  </div>
</template>
