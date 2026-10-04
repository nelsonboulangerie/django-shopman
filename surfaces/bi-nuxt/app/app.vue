<script setup lang="ts">
// Shell do B.I. Casca fina: produção/vendas/caixa/clientes são páginas
// próprias (pages/), e o shell segura o outlet + a chrome + o gate de operador.
//
// Gate: `backstage.view_bi` — leitura analítica cross-suite é persona de
// gestão (ADR-021 §5), não de quem opera o turno.
const OPERATOR_PERM = "backstage.view_bi";
const { canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useOperatorWindowTitle();
</script>

<template>
  <!-- `data-suite="v3"`: o B.I. veste a camada visual da suíte (V4-BI, prévia
       `bi-sobra4.html`). Os primitivos do kit leem esse atributo. -->
  <div class="flex min-h-dvh bg-background text-foreground" data-suite="v3">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo de conexão (kit) — global, só aparece offline. -->
    <OfflineBanner />
    <!-- Rail da suíte (kit): o selo do app (Central), as oito leituras, Avisos,
         Bloquear e o menu do operador. Do tablet para cima; no celular as seções vão
         para a barra do polegar, no fim da coluna de conteúdo. -->
    <BiNav
      v-if="canIdentify"
      place="rail"
      :hub-url="hubUrl"
      :operator-name="operator?.name"
      @lock="lock"
    />
    <div class="flex min-w-0 flex-1 flex-col">
      <NuxtPage />
      <BiNav v-if="canIdentify && !locked && !mustChange" place="bar" :operator-name="operator?.name" @lock="lock" />
    </div>
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
         alpha subia a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="sessionUnavailable" scope="o painel de B.I." @retry="refresh()" />
    <OperatorLogin v-if="!canIdentify && !sessionUnavailable" />
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
