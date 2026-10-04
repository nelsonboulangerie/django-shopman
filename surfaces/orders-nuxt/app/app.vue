<script setup lang="ts">
// Gestor de Pedidos surface shell. Thin shell — the order hub is a board + detail,
// each at its own URL, so it uses pages/ routing (like the KDS, unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C): when the gate is ON and nobody unlocked, a PIN/badge is
// required. Gated OFF → never shows.
// Quem gerencia pedidos OU quem expede (SUITE-UX §15: a Saída da Cozinha mora na
// coluna Saída daqui). A trava do Gestor é a primeira (`shop.manage_orders`). É a
// mesma de `GESTOR_SURFACE_PERM` (useGestorAccess), escrita por extenso porque o
// teste do tile da Central (`test_hub_projection_identity`) lê esta linha.
const OPERATOR_PERM = "shop.manage_orders|backstage.operate_kds";
const { hasDirty: cashDraftDirty } = useOrderCashDrafts();
const { hasPending: intentionPending } = useOrderIntention();
function protectSessionExit(event: BeforeUnloadEvent) {
  if (!cashDraftDirty.value && !intentionPending.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", protectSessionExit));
onBeforeUnmount(() => window.removeEventListener("beforeunload", protectSessionExit));
const { canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

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

useOperatorWindowTitle();
</script>

<template>
  <!-- `data-suite="v3"`: o Gestor é o piloto da camada visual da suíte (UX-KIT-V1). Os
       primitivos do kit leem esse atributo para vestir o visual das prévias. -->
  <div class="flex min-h-dvh bg-background text-foreground" data-suite="v3">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit) — global, só aparece offline (paridade c/ POS/KDS/hub). -->
    <OfflineBanner />
    <!-- Rail da suíte (kit): o selo do app (Central), as seções do Gestor, alertas e
         avisos, Bloquear e o menu do operador. Do tablet para cima; no celular as
         seções vão para a barra do polegar, no fim da coluna de conteúdo. -->
    <GestorNav
      v-if="canIdentify"
      place="rail"
      :hub-url="hubUrl"
      :operator-name="operator?.name"
      @lock="lock"
    />
    <div class="flex min-w-0 flex-1 flex-col">
      <div v-show="canIdentify && !locked && !mustChange" class="flex min-h-0 flex-1 flex-col">
        <NuxtPage :key="workspaceOwner ?? 'unidentified'" />
      </div>
      <GestorNav v-if="canIdentify && !locked && !mustChange" place="bar" />
    </div>
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
         alpha subia a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="sessionUnavailable" scope="os pedidos" @retry="refresh()" />
    <OperatorLogin v-if="!canIdentify && !sessionUnavailable" :reload-on-success="false" @success="restoreAuthenticatedWorkspace" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <OperatorStationSetup
      v-if="stationSetup.offer.value"
      @done="stationSetup.done()"
      @dismiss="stationSetup.dismiss()"
      @unavailable="stationSetup.dismiss({ remember: false })"
    />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </div>
</template>
