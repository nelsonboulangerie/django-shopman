<script setup lang="ts">
// Shell do Marketing. Casca fina: fila, ajustes e histórico são páginas próprias
// (pages/), e o shell segura o outlet + a chrome + o gate de operador.
//
// Fase 2 (WP-FASE2-UX-OPERADOR, onda do Marketing): o app mora no shell da suíte, o
// mesmo do Gestor (`OperatorSuiteShell`): barra lateral em três estados na mesa,
// gaveta pelo ☰ e barra inferior de 3 a 5 vagas abaixo de `lg`. As seções vêm de
// `useMarketingSections`, uma fonte só.
//
// O destrave só pede a capability de entrar. A autorização de cada Action é
// revalidada no backend; abrir o app nunca concede publicação por herança.
const OPERATOR_PERM = "shop.view_marketing";
const {
  canIdentify,
  sessionState,
  sessionUnavailable,
  operator,
  lock,
  refresh: refreshSession,
  locked,
  stationRef,
} = useOperatorLock(OPERATOR_PERM);
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const publicConfig = useRuntimeConfig().public;
const hubUrl = publicConfig.operatorHubUrl as string;
// A cor do app (a mesma do selo na barra lateral) vira `--app-color` no `<html>`: as
// miniaturas da fila de decisões e o carimbo do selo usam o tom dela. No `<html>`, e
// não no shell, porque o selo é diálogo teleportado para fora dele.
const appColor = (
  publicConfig.operatorPwa as { identity?: { color?: string } } | undefined
)?.identity?.color;
if (appColor) useHead({ htmlAttrs: { style: `--app-color: ${appColor}` } });
const { attrsFor: appLinkAttrsFor } = useOperatorAppLink();
const hubLink = computed(() => appLinkAttrsFor(hubUrl));

const { sections, activeSection } = useMarketingSections();

// Avisos (MKT-01/T-13): a caixa do kit, a mesma em todo app. As decisões entram nela
// como UM resumo que leva à fila, não como uma segunda lista (decisão do dono de
// 03/10/2026: "o sino abre a mesma fila"). A caixa pessoal (avisos de acesso) entra na
// outra aba.
const { decisionCount } = useMarketingDecisions();
provideOperatorInboxAlerts(() => ({
  title: "Decisões",
  emptyText: "Nenhuma decisão esperando você.",
  count: decisionCount.value,
  items: decisionCount.value
    ? [
        {
          key: "decisions",
          tone: "warning" as const,
          message:
            decisionCount.value === 1
              ? "1 decisão espera você."
              : `${decisionCount.value} decisões esperam você.`,
          meta: "O prazo mais curto primeiro.",
          href: "/",
          hrefLabel: "Abrir a fila de decisões",
        },
      ]
    : [],
}));

useOperatorWindowTitle();

watch(sessionState, async (next, previous) => {
  if (next !== "authenticated" || previous === "authenticated") return;
  await nextTick();
  const heading = document.querySelector<HTMLElement>(
    "[data-marketing-app-root] main h1",
  );
  heading?.setAttribute("tabindex", "-1");
  // O foco é para o leitor de tela anunciar a tela; sem anel (não é controle).
  heading?.focus({ preventScroll: true, focusVisible: false } as FocusOptions);
});
</script>

<template>
  <OperatorAppRoot>
    <!-- NuxtPage fica presente para o router, mas a página recebida pelo slot só é
         instanciada depois do gate. Isso evita tanto fetch anônimo quanto o falso
         warning do Nuxt causado por remover condicionalmente o próprio outlet. -->
    <NuxtPage v-slot="{ Component }">
      <div
        data-marketing-app-root
        class="flex min-h-dvh bg-background text-foreground"
      >
        <NuxtRouteAnnouncer />
        <!-- Aviso calmo de conexão (kit): global, só aparece offline. -->
        <OfflineBanner />
        <!-- O app protegido só existe depois de sessão + capability confirmadas. O
             login deixou de ser uma cortina sobre fetches e timers já montados. -->
        <OperatorSuiteShell
          v-if="sessionState === 'authenticated'"
          storage-key="marketing"
          :sections="sections"
          :current="activeSection"
          label="Seções do Marketing"
          :operator-name="operator?.name"
          @lock="lock"
        >
          <div class="flex min-h-0 flex-1 flex-col">
            <component :is="Component" />
          </div>
          <!-- A caixa pessoal (SSE, poll, "visto"): uma só, em qualquer largura. -->
          <MarketingInboxLive />
        </OperatorSuiteShell>

        <main
          v-else-if="sessionUnavailable"
          class="grid min-h-dvh flex-1 place-items-center p-4"
        >
          <NuxtEmpty
            icon="i-lucide-wifi-off"
            title="Não foi possível conferir seu acesso"
            description="O Marketing continua fechado e nenhum dado de Marketing foi carregado."
            :actions="[
              {
                label: 'Tentar de novo',
                icon: 'i-lucide-refresh-cw',
                color: 'neutral',
                variant: 'outline',
                onClick: () => refreshSession(),
              },
            ]"
          />
        </main>

        <main
          v-else-if="sessionState === 'checking'"
          class="grid min-h-dvh flex-1 place-items-center p-4"
          role="status"
          aria-busy="true"
        >
          <NuxtEmpty
            loading
            title="Conferindo seu acesso ao Marketing"
            variant="naked"
          />
        </main>

        <main
          v-else-if="sessionState === 'forbidden'"
          class="grid min-h-dvh flex-1 place-items-center p-4"
        >
          <!-- Mesma regra do ícone da Central na barra lateral: instalado, ele abre na
               janela DELA (ver operator-kit/app/presentation/appLaunch.ts). -->
          <NuxtEmpty
            icon="i-lucide-shield-x"
            title="Seu acesso não inclui o Marketing"
            description="Entrar de novo não resolve. Peça a um responsável o acesso ao Marketing."
            :actions="[
              {
                label: 'Voltar à Central',
                color: 'neutral',
                variant: 'outline',
                href: hubUrl,
                target: hubLink.target,
                rel: hubLink.rel,
              },
            ]"
          />
        </main>

        <OperatorLogin
          v-else-if="sessionState === 'expired' || !canIdentify"
          role="main"
          :expired="sessionState === 'expired'"
          :reload-on-success="false"
        />
        <OperatorLock v-else :perm="OPERATOR_PERM" />
        <OperatorStationSetup
          v-if="stationSetup.offer.value"
          @done="stationSetup.done()"
          @dismiss="stationSetup.dismiss()"
          @unavailable="stationSetup.dismiss({ remember: false })"
        />
        <OperatorSonner />
        <OperatorPwaRuntime />
      </div>
    </NuxtPage>
  </OperatorAppRoot>
</template>
