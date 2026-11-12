<script setup lang="ts">
import { operatorAlertToInbox } from "../../operator-kit/app/presentation/suiteChrome";
import { gestorSwitcherSections } from "~/presentation/gestorSections";

// Gestor de Pedidos surface shell. Thin shell — the order hub is a board + detail,
// each at its own URL, so it uses pages/ routing (like the KDS, unlike the POS
// kiosk single-shell). The shell holds the page outlet + chrome + the operator
// lock overlay (Opção C): when the gate is ON and nobody unlocked, a PIN/badge is
// required. Gated OFF → never shows.
// Quem gerencia pedidos OU quem expede (SUITE-UX §15: a Saída da Cozinha mora na
// coluna Saída daqui). A trava do Gestor é a primeira (`shop.manage_orders`). É a
// mesma de `GESTOR_SURFACE_PERM` (useGestorAccess), escrita por extenso porque o
// teste do tile da Central (`test_hub_projection_identity`) lê esta linha.
const OPERATOR_PERM = "shop.manage_orders|backstage.operate_kds|shop.manage_catalog";
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
// O widget do iFood (chat com o cliente) mora na casca, não no detalhe: a mensagem
// nova do cliente aparece no botão do iFood em qualquer tela do Gestor. Só sobe
// depois da trava liberar a página, e só se a loja ligou (DEV-2026-018).
const ifoodWidget = useIFoodWidget();
watch(
  () => surface.value.showPage,
  (showPage) => {
    if (showPage) void ifoodWidget.start();
  },
  { immediate: true },
);
const route = useRoute();
const { landingPath } = useGestorAccess();
const redirectingToRoleLanding = computed(
  () =>
    surface.value.showPage &&
    route.path === "/" &&
    landingPath.value === "/catalog",
);
watch(
  [() => surface.value.showPage, () => route.path, landingPath],
  ([showPage, path, landing]) => {
    if (showPage && path === "/" && landing === "/catalog") {
      void navigateTo("/catalog", { replace: true });
    }
  },
  { immediate: true },
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

const { sections, settings, current, denied } = useGestorSections();
const routeAccess = useGestorRouteAccess();
// As seções de Ajustes dependem de permissão lida por uma chave que leva o id de quem
// opera, e no servidor a sessão ainda não chegou quando a chave nasce: lá a resposta
// vem de uma chave, aqui de outra. Elas entram depois de montar, para o servidor e a
// hidratação desenharem a mesma barra de baixo.
const mounted = ref(false);
onMounted(() => {
  mounted.value = true;
});
// O trocador lista tudo, pela forma; as do chão são as da barra de baixo no celular
// (`gestorSwitcherSections`).
const switcherSections = computed(() =>
  gestorSwitcherSections(sections.value, mounted.value ? settings.value : []),
);
const { alerts, activeCount, ack, accept, isAccepting } = useAlerts();
provideOperatorInboxAlerts(() => ({
  title: "Gerais",
  emptyText: "Nenhum alerta de pedido agora.",
  items: alerts.value.map(operatorAlertToInbox),
  count: activeCount.value,
  ack: (key) => {
    const alert = alerts.value.find((item) => item.pk === key);
    if (alert) return ack(alert);
  },
  // O gesto direto do aviso (P2-19: "Aceitar" no pedido parado sem aceite).
  act: async (key) => {
    const alert = alerts.value.find((item) => item.pk === key);
    if (alert) await accept(alert);
  },
  isPending: (key) => isAccepting(Number(key)),
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
        v-if="surface.showPage && !redirectingToRoleLanding"
        storage-key="gestor"
        :sections="sections"
        :current="current"
        :switcher-sections="switcherSections"
        default-form="floor"
        floor-bar
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
          <!-- URL direta numa seção de Ajustes fora do acesso: a recusa dita como
               recusa, não como "Sem conexão" (beta 05/11, GES-08). -->
          <div
            v-if="mounted && denied"
            class="grid flex-1 place-items-center p-4"
            data-settings-denied
          >
            <OperatorScreenState state="forbidden" :what="denied">
              <template #actions>
                <NuxtButton label="Voltar aos pedidos" to="/" color="neutral" variant="outline" />
              </template>
            </OperatorScreenState>
          </div>
          <!-- A régua do servidor para o que a lista não cobre (o Histórico, por exemplo):
               a recusa no lugar da página, sem "Tentar de novo" (beta 05/11, CEN-05 e GES-17). -->
          <main
            v-else-if="routeAccess.denied.value"
            class="flex min-h-0 flex-1 flex-col"
            data-gestor-route-forbidden
          >
            <section class="grid flex-1 place-items-center p-4 sm:p-6">
              <OperatorScreenState state="forbidden" :what="routeAccess.what.value" />
            </section>
          </main>
          <NuxtPage v-else :key="workspaceOwner ?? 'unidentified'" />
        </div>
      </OperatorSuiteShell>
      <OperatorSurfaceForbidden v-else-if="surface.showForbidden" :perm="OPERATOR_PERM" />
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
