<script setup lang="ts">
// Shell do B.I. Casca fina: produção/vendas/caixa/clientes são páginas
// próprias (pages/), e o shell segura o outlet + a chrome + o gate de operador.
//
// Gate: `backstage.view_bi` — leitura analítica cross-suite é persona de
// gestão (ADR-021 §5), não de quem opera o turno.
const OPERATOR_PERM = "backstage.view_bi";
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
// Uma única decisão canônica (kit) separa autenticação, autorização, rede e trava,
// como no Gestor: `canIdentify` sozinho só diz que a antessala respondeu, não
// autoriza a página, e montar o outlet antes disto dispara leituras protegidas.
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
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

// As oito leituras, com a janela de análise na query de cada uma: trocar de seção
// não troca de período, e o link colado abre a mesma leitura.
const { sections } = useBiSections();

useOperatorWindowTitle();
</script>

<template>
  <OperatorAppRoot>
    <!-- O B.I. não veste mais a pele legada `suite:` (sem `data-suite`): a identidade
         vem dos tokens Shopman e do tema global do Nuxt UI, como no Gestor. -->
    <div class="flex min-h-dvh bg-background text-foreground" data-bi-app>
      <NuxtRouteAnnouncer />
      <!-- Aviso calmo de conexão (kit) — global, só aparece offline. -->
      <OfflineBanner />
      <!-- A casca canônica da suíte (kit): rail de ícones do tablet deitado para cima,
           barra de seções com "Mais" no celular e no tablet em pé. -->
      <OperatorSuiteShell
        v-if="surface.showPage"
        storage-key="bi"
        :sections="sections"
        label="Seções do B.I."
        :operator-name="operator?.name"
        @lock="lock"
      >
        <div class="flex min-h-0 flex-1 flex-col">
          <NuxtPage />
        </div>
      </OperatorSuiteShell>
      <main v-else-if="surface.showForbidden" class="grid min-h-dvh flex-1 place-items-center p-4">
        <NuxtEmpty
          icon="i-lucide-shield-x"
          title="Seu acesso não inclui o B.I."
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
          <p class="text-sm text-muted-foreground">Conferindo seu acesso ao B.I.…</p>
        </div>
      </main>
      <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
           alpha subia a tela de senha com a sessão viva. -->
      <OperatorSessionUnavailable v-if="surface.showUnavailable" scope="o painel de B.I." @retry="refresh()" />
      <OperatorLogin v-if="surface.showLogin" :expired="sessionState === 'expired'" />
      <OperatorLock v-else-if="surface.showLock" :perm="OPERATOR_PERM" />
      <OperatorStationSetup
        v-if="stationSetup.offer.value"
        @done="stationSetup.done()"
        @dismiss="stationSetup.dismiss()"
        @unavailable="stationSetup.dismiss({ remember: false })"
      />
      <OperatorSonner />
      <OperatorPwaRuntime />
    </div>
  </OperatorAppRoot>
</template>
