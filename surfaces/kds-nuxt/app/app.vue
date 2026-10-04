<script setup lang="ts">
// KDS surface shell (Arc 2). Thin shell — the KDS is a multi-display surface
// (station picker, per-station board, customer pickup board), each opened at its
// own URL on a physical kitchen screen, so it uses pages/ routing (unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C). The overlay covers the OPERATOR screens only — never the
// PUBLIC customer pickup board (/pickup), which has no auth. Gated OFF → never shows.
const OPERATOR_PERM = "backstage.operate_kds";
const { canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);

const route = useRoute();
const isCustomerBoard = computed(() => route.path.startsWith("/pickup"));
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useOperatorWindowTitle();
</script>

<template>
  <!-- `data-suite="v3"`: a Cozinha veste a camada visual da suíte (UX-KIT-V1, prévia v4
       `cozinha-estacao4.html`). Os primitivos do kit leem esse atributo. -->
  <div class="min-h-dvh bg-background text-foreground" data-suite="v3">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo e global de conexão (kit) — só aparece offline (paridade POS/Gestor/Produção). -->
    <OfflineBanner />
    <!-- Painel público de retirada: tela cheia, sem rail e sem auth. -->
    <NuxtPage v-if="isCustomerBoard" />
    <!-- Telas de operador: rail da suíte (kit) do tablet para cima; no celular as
         seções vão para a barra do polegar, no fim da coluna de conteúdo. -->
    <div v-else class="flex min-h-dvh">
      <KdsNav
        v-if="canIdentify"
        place="rail"
        :hub-url="hubUrl"
        :operator-name="operator?.name"
        @lock="lock"
      />
      <div class="flex min-w-0 flex-1 flex-col">
        <NuxtPage />
        <KdsNav v-if="canIdentify && !locked && !mustChange" place="bar" />
      </div>
      <KdsSettingsDialog v-if="canIdentify" />
    </div>
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
         alpha subia a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="sessionUnavailable" scope="a cozinha" @retry="refresh()" />
    <OperatorLogin v-if="!canIdentify && !sessionUnavailable && !isCustomerBoard" />
    <OperatorLock
      v-else-if="(locked || mustChange) && !isCustomerBoard"
      :perm="OPERATOR_PERM"
    />
    <OperatorStationSetup
      v-if="stationSetup.offer.value && !isCustomerBoard"
      @done="stationSetup.done()"
      @dismiss="stationSetup.dismiss()"
      @unavailable="stationSetup.dismiss({ remember: false })"
    />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </div>
</template>
