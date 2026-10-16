<script setup lang="ts">
// Casca da Produção (prod.). Duas classes de tela:
//   · telas de OPERADOR (planejamento, preparação, abertura, fechamento, qualidade,
//     timers, ajustes) → o shell da suíte (`OperatorSuiteShell` do kit), como o Gestor
//     e o B.I.: barra lateral em três estados na mesa, gaveta pelo ☰ e barra inferior
//     de 3 a 5 vagas no celular;
//   · o Letreiro (`/board`) → KIOSK de TV em tela cheia, em casca própria SEM
//     navegação (exceção declarada da fase 2: a TV não tem quem toque numa barra), mas
//     DENTRO do mesmo gate (a previsão exige backstage.operate_production).
// O menuboard paralelo foi aposentado: a TV canônica pertence ao Django, por ref e
// credencial. D4 definirá refs/cutover; este app não adivinha um destino.
import { operatorAlertToInbox } from "../../operator-kit/app/presentation/suiteChrome";

const OPERATOR_PERM = "backstage.operate_production";
const {
  canIdentify,
  sessionState,
  sessionUnavailable,
  refresh,
  locked,
  mustChange,
  operator,
  lock,
  stationRef,
} = useOperatorLock(OPERATOR_PERM);
// Uma decisão canônica (kit) separa autenticação, autorização, rede e trava, como no
// Gestor e no B.I.: `canIdentify` sozinho só diz que a antessala respondeu.
const surface = computed(() =>
  operatorSurfaceGate({
    sessionState: sessionState.value,
    canIdentify: canIdentify.value,
    sessionUnavailable: sessionUnavailable.value,
    locked: locked.value,
    mustChange: mustChange.value,
    harness: false,
  }),
);
const route = useRoute();
const isKiosk = computed(() => route.path.startsWith("/board"));
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

// O ciclo do lote (Alt+1 a Alt+5), Timers e Ajustes (Receitas, Relatórios, Letreiro).
const { sections } = useProductionSections();

// Avisos da operação (OperatorAlert) na caixa do kit, ao lado da caixa pessoal.
const { alerts, activeCount, ack, isPending } = useAlerts();
provideOperatorInboxAlerts(() => ({
  title: "Gerais",
  emptyText: "Nenhum alerta agora.",
  items: alerts.value.map(operatorAlertToInbox),
  count: activeCount.value,
  ack: (key) => {
    const alert = alerts.value.find((item) => item.pk === key);
    if (alert) return ack(alert);
  },
  isPending: (key) => isPending(Number(key)),
}));

useOperatorWindowTitle();
</script>

<template>
  <OperatorAppRoot>
    <div class="flex min-h-dvh bg-background text-foreground" data-production-app>
      <NuxtRouteAnnouncer />
      <!-- Aviso calmo e global de conexão (kit), só aparece offline. -->
      <OfflineBanner />
      <!-- O Letreiro: tela cheia, sem barra lateral, sem barra inferior. -->
      <div v-if="isKiosk && surface.showPage" class="min-w-0 flex-1" data-production-kiosk>
        <NuxtPage />
      </div>
      <OperatorSuiteShell
        v-else-if="surface.showPage"
        storage-key="production"
        :sections="sections"
        label="Telas da produção"
        :operator-name="operator?.name"
        @lock="lock"
      >
        <div class="flex min-h-0 flex-1 flex-col">
          <OperatorStationSetup
            v-if="stationSetup.offer.value"
            mode="inline"
            @done="stationSetup.done()"
            @dismiss="stationSetup.dismiss()"
            @unavailable="stationSetup.dismiss({ remember: false })"
          />
          <NuxtPage />
        </div>
      </OperatorSuiteShell>
      <main v-else-if="surface.showForbidden" class="grid min-h-dvh flex-1 place-items-center p-4">
        <NuxtEmpty
          icon="i-lucide-shield-x"
          title="Seu acesso não inclui a Produção"
          description="Peça a um responsável a permissão de acesso. Entrar novamente não concede essa permissão."
        />
      </main>
      <main
        v-else-if="surface.showChecking"
        class="grid min-h-dvh flex-1 place-items-center p-4"
        role="status"
        aria-busy="true"
      >
        <div class="grid w-full max-w-sm gap-3 text-center">
          <NuxtSkeleton class="mx-auto h-12 w-12" />
          <p class="text-sm text-muted-foreground">Conferindo seu acesso à Produção…</p>
        </div>
      </main>
      <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
           alpha subia a tela de senha com a sessão viva. -->
      <OperatorSessionUnavailable v-if="surface.showUnavailable" scope="a produção" @retry="refresh()" />
      <OperatorLogin v-if="surface.showLogin" :expired="sessionState === 'expired'" />
      <OperatorLock v-else-if="surface.showLock" :perm="OPERATOR_PERM" />
      <OperatorSonner />
      <OperatorPwaRuntime />
    </div>
  </OperatorAppRoot>
</template>
