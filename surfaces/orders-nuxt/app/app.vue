<script setup lang="ts">
import { operatorAlertToInbox } from "../../operator-kit/app/presentation/suiteChrome";

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
onBeforeUnmount(() =>
  window.removeEventListener("beforeunload", protectSessionExit),
);
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
// Uma única decisão canônica separa autenticação, autorização, rede e trava.
// `canIdentify` sozinho só diz que a antessala respondeu; ele não autoriza a
// página. Montar o outlet antes desta decisão dispara leituras protegidas durante
// o checking/lock e pode transformar uma resposta transitória em novo login.
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

// Keep drafts through a lock/re-identification by the same person. A different
// identified person receives a new page instance and their own read-cache keys.
const workspaceOwner = ref(operator.value?.id ?? null);
watch(
  () => operator.value?.id,
  (id) => {
    if (id != null) workspaceOwner.value = id;
  },
);

const station = useStationLock();
async function restoreAuthenticatedWorkspace() {
  station.clear();
  await refreshNuxtData();
}

const { sections, current } = useGestorSections();
const { alerts, activeCount, ack } = useAlerts();
provideOperatorInboxAlerts(() => ({
  title: "Gerais",
  emptyText: "Nenhum alerta de pedido agora.",
  items: alerts.value.map(operatorAlertToInbox),
  count: activeCount.value,
  ack: (key) => {
    const alert = alerts.value.find((item) => item.pk === key);
    if (alert) return ack(alert);
  },
}));

useOperatorWindowTitle();
</script>

<template>
  <OperatorAppRoot>
    <!-- O Gestor não ativa mais a pele legada `suite:`. A identidade visual vem
         apenas dos tokens Shopman e do tema global do Nuxt UI. -->
    <div class="flex min-h-dvh bg-background text-foreground" data-orders-app>
      <NuxtRouteAnnouncer />
      <!-- Aviso calmo de conexão (kit) — global, só aparece offline (paridade c/ POS/KDS/hub). -->
      <OfflineBanner />
      <OperatorSuiteShell
        v-if="surface.showPage"
        storage-key="gestor"
        :sections="sections"
        :current="current"
        label="Seções do Gestor"
        :operator-name="operator?.name"
        @lock="lock"
      >
        <div class="flex min-h-0 flex-1 flex-col">
          <OperatorStationSetup
            v-if="stationSetup.offer.value"
            mode="inline"
            empty-to="/workstations"
            @done="stationSetup.done()"
            @dismiss="stationSetup.dismiss()"
            @unavailable="stationSetup.dismiss({ remember: false })"
          />
          <NuxtPage :key="workspaceOwner ?? 'unidentified'" />
        </div>
      </OperatorSuiteShell>
      <main
        v-else-if="surface.showForbidden"
        class="grid min-h-dvh flex-1 place-items-center p-4"
      >
        <NuxtEmpty
          icon="i-lucide-shield-x"
          title="Seu acesso não inclui o Gestor de pedidos"
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
          <p class="text-sm text-muted-foreground">
            Conferindo seu acesso ao Gestor de pedidos…
          </p>
        </div>
      </main>
      <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
           alpha subia a tela de senha com a sessão viva. -->
      <OperatorSessionUnavailable
        v-if="surface.showUnavailable"
        scope="os pedidos"
        @retry="refresh()"
      />
      <OperatorLogin
        v-if="surface.showLogin"
        :expired="sessionState === 'expired'"
        :reload-on-success="false"
        @success="restoreAuthenticatedWorkspace"
      />
      <OperatorLock v-else-if="surface.showLock" :perm="OPERATOR_PERM" />
      <OperatorPwaRuntime />
    </div>
  </OperatorAppRoot>
</template>
