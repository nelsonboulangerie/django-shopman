<script setup lang="ts">
// Gestor de Pedidos surface shell. Thin shell — the order hub is a board + detail,
// each at its own URL, so it uses pages/ routing (like the KDS, unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C): when the gate is ON and nobody unlocked, a PIN/badge is
// required. Gated OFF → never shows.
const OPERATOR_PERM = "shop.manage_orders";
const { canIdentify, locked, mustChange, operator, lock } = useOperatorLock(OPERATOR_PERM);

// Keep drafts through a lock/re-identification by the same person. A different
// identified person receives a new page instance and their own read-cache keys.
const workspaceOwner = ref(operator.value?.id ?? null);
watch(() => operator.value?.id, (id) => { if (id != null) workspaceOwner.value = id; });

const station = useStationLock();
async function restoreAuthenticatedWorkspace() {
  station.clear();
  await refreshNuxtData();
}

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useHead({ title: "Gestor de Pedidos" });
</script>

<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit) — global, só aparece offline (paridade c/ POS/KDS/hub). -->
    <OfflineBanner />
    <!-- Rail de operador canônico (kit): funções comuns (Central, operador, tema). Fica
         fixo enquanto o conteúdo rola. Colapsado → não renderiza (some de verdade). -->
    <div v-if="canIdentify" class="sticky top-0 flex h-screen shrink-0 print:hidden">
      <OperatorRail
        app-icon="clipboard-list"
        app-label="Gestor"
        :central-url="hubUrl"
        :operator-name="operator?.name"
        @lock="lock"
      />
    </div>
    <div class="flex min-w-0 flex-1 flex-col">
      <!-- Cabeçalho de seção: controle do rail + nav do Gestor. -->
      <GestorTopBar v-if="canIdentify" />
      <div v-show="canIdentify && !locked && !mustChange" class="flex min-h-0 flex-1 flex-col">
        <NuxtPage :key="workspaceOwner ?? 'unidentified'" />
      </div>
    </div>
    <OperatorLogin v-if="!canIdentify" :reload-on-success="false" @success="restoreAuthenticatedWorkspace" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <OperatorSonner />
  </div>
</template>
