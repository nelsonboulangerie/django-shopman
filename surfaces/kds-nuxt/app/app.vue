<script setup lang="ts">
// Shell da Cozinha. A Cozinha abre cada tela na sua URL (a lista de estações, a bancada
// de cada estação, o Painel de retirada), por isso usa pages/. As telas de operador
// moram no shell da suíte (`OperatorSuiteShell`, fase 2): barra lateral em três estados
// na mesa, gaveta pelo ☰ e barra inferior abaixo de `lg`, com as estações da casa pelo
// nome (`kdsShellSections`), a Saída levando ao Gestor e Ajustes no pé.
//
// Exceção declarada: o Painel de retirada (`/pickup`) é a TV do salão, para o cliente.
// Fica fora do shell, em tela cheia, sem navegação e sem login; a trava de operador
// nunca o cobre.
const OPERATOR_PERM = "backstage.operate_kds";
const { canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);

const route = useRoute();
const isCustomerBoard = computed(() => route.path.startsWith("/pickup"));
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const { sections, current } = useKdsSections();
const settingsOpen = useKdsSettingsOpen();
// Ajustes não é rota: abre o painel de Ajustes da estação.
function onSelect(key: string) {
  if (key === "settings") settingsOpen.value = true;
}

useOperatorWindowTitle();
</script>

<template>
  <OperatorAppRoot>
    <div class="min-h-dvh bg-background text-foreground" data-kds-app>
      <NuxtRouteAnnouncer />
      <!-- Aviso calmo e global de conexão (kit): só aparece offline. -->
      <OfflineBanner />
      <!-- Painel público de retirada: tela cheia, sem shell e sem login. A pele da
           suíte (`data-suite`) segue só nele, que não migra (tela do cliente). -->
      <div v-if="isCustomerBoard" data-suite="v3">
        <NuxtPage />
      </div>
      <OperatorSuiteShell
        v-else-if="canIdentify"
        storage-key="kds"
        :sections="sections"
        :current="current"
        label="Seções da Cozinha"
        :operator-name="operator?.name"
        @select="onSelect"
        @lock="lock"
      >
        <!-- A trava cobre a tela por cima; o quadro segue montado por baixo e volta
             no mesmo estado quando alguém se identifica. -->
        <NuxtPage />
      </OperatorSuiteShell>
      <KdsSettingsDialog v-if="canIdentify && !isCustomerBoard" />
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
  </OperatorAppRoot>
</template>
