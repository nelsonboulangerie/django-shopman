<script setup lang="ts">
// Production surface shell (prod.). Thin shell com duas classes de
// tela (verificadas endpoint a endpoint):
//   · telas de OPERADOR (planejamento/preparação/abertura/fechamento/qualidade) → rail da
//     suíte (kit, `ProductionNav`) + conteúdo, atrás do gate de operador;
//   · painel (Lotes) → KIOSK de operador em tela cheia (a previsão exige
//     backstage.operate_production) — FORA do rail, mas DENTRO do gate;
// O menuboard paralelo foi aposentado: a TV canônica pertence ao Django, por ref e
// credencial. D4 definirá refs/cutover; este app não adivinha um destino.
const OPERATOR_PERM = "backstage.operate_production";
const { canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);
const route = useRoute();
const isKiosk = computed(() => route.path.startsWith("/board"));
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useOperatorWindowTitle();
</script>

<template>
  <!-- `data-suite="v3"`: a Produção veste a camada visual da suíte (V4-PROD, modelo do
       Gestor). O Letreiro (kiosk) também: tokens e tipografia da suíte, sem rail. -->
  <div class="min-h-dvh bg-background text-foreground" data-suite="v3">
    <NuxtRouteAnnouncer />
    <!-- Aviso calmo e global de conexão (kit) — só aparece offline (paridade c/ POS/KDS/Gestor). -->
    <OfflineBanner />
    <!-- Painel de operador em modo kiosk: tela cheia, sem rail, ainda atrás do gate. -->
    <NuxtPage v-if="isKiosk" />
    <!-- Telas de operador: rail da suíte (tablet e desktop) + conteúdo; no celular,
         as etapas vão para a barra do polegar no fim da coluna de conteúdo. -->
    <div v-else class="flex min-h-dvh">
      <!-- O ciclo do lote, Timers e, no pé, Receitas, Relatórios (persona gestor, só
           com a perm fina) e o Letreiro (kiosk de TV, tela cheia). -->
      <ProductionNav
        v-if="canIdentify"
        place="rail"
        :hub-url="hubUrl"
        :operator-name="operator?.name"
        @lock="lock"
      />
      <div class="flex min-w-0 flex-1 flex-col">
        <NuxtPage />
        <ProductionNav v-if="canIdentify && !locked && !mustChange" place="bar" />
      </div>
    </div>
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
         alpha subia a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="sessionUnavailable" scope="a produção" @retry="refresh()" />
    <OperatorLogin v-if="!canIdentify && !sessionUnavailable" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <OperatorStationSetup
      v-if="stationSetup.offer.value && !isKiosk"
      @done="stationSetup.done()"
      @dismiss="stationSetup.dismiss()"
      @unavailable="stationSetup.dismiss({ remember: false })"
    />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </div>
</template>
