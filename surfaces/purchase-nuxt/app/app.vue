<script setup lang="ts">
import { baseSectionOf, purchaseSections } from "~/presentation/purchaseSections";
import type { PurchaseView } from "~/types/purchase";

// Compras no shell da suíte (WP-FASE2-UX-OPERADOR, onda do Compras), como o Gestor:
// barra lateral em três estados na mesa, gaveta e barra inferior abaixo de `lg`. Cada
// seção é uma rota (Painel `/`, Comprar `/buy`, Receber `/receive`, Base `/base/…`),
// e as quatro dividem o mesmo carregamento (`usePurchaseDesk`, em `useState`).
const OPERATOR_PERM = "backstage.operate_purchase";
const { canIdentify, sessionState, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);
// Uma decisão só separa autenticação, autorização, rede e trava (a mesma do Gestor):
// o conteúdo só monta com o acesso decidido, para nenhuma leitura protegida correr
// durante a conferência e virar um login falso.
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
// Vincular o dispositivo a um posto (kit, a mesma regra dos apps): oferta, não parede.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const { view, baseView, metrics, receiptTotalPending, pending, backendReady, refresh: refreshPurchase } = usePurchaseDesk();

// A hora da última leitura útil da base (o selo de cada tela). O Compras não tem SSE:
// a leitura acontece ao abrir e em Atualizar, e o selo diz isso sem fingir ao vivo.
const readAt = useState("purchase-read-at", () => "");
watch(
  [pending, backendReady],
  ([isPending, ready]) => {
    if (!isPending && ready) {
      readAt.value = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    }
  },
  { immediate: true },
);
// R atualiza a tela (o item "Atualizar" do ⋯ de toda tela), fora de campo de texto e
// de diálogo aberto.
onKeyStroke(["r", "R"], (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.repeat) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) return;
  void refreshPurchase();
});
const sections = computed(() =>
  purchaseSections({ urgentMaterials: metrics.value.urgentMaterials, receivePending: receiptTotalPending.value }),
);

// A seção e a sub-seção da Base vêm da rota. O carregamento da Contagem (e o que mais
// depender da vista) segue a mesma fonte.
const route = useRoute();
function viewOf(path: string): PurchaseView {
  if (path.startsWith("/buy")) return "buy";
  if (path.startsWith("/receive")) return "receive";
  if (path.startsWith("/base")) return "base";
  return "panel";
}
watch(
  () => route.path,
  (path) => {
    view.value = viewOf(path);
    const base = baseSectionOf(path);
    if (base) baseView.value = base;
  },
  { immediate: true },
);

useOperatorWindowTitle();
</script>

<template>
  <OperatorAppRoot>
    <div class="flex min-h-dvh bg-background text-foreground" data-purchase-app>
      <NuxtRouteAnnouncer />
      <OfflineBanner />
      <OperatorSuiteShell
        v-if="surface.showPage"
        storage-key="purchase"
        :sections="sections"
        label="Seções do Compras"
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
          title="Seu acesso não inclui o Compras"
          description="Peça a um responsável a permissão de comprar e receber insumos. Entrar novamente não concede essa permissão."
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
          <p class="text-sm text-muted-foreground">Conferindo seu acesso ao Compras…</p>
        </div>
      </main>
      <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do alpha subia
           a tela de senha com a sessão viva. -->
      <OperatorSessionUnavailable v-if="surface.showUnavailable" scope="as compras" @retry="refresh()" />
      <OperatorLogin
        v-if="surface.showLogin"
        :expired="sessionState === 'expired'"
        :title="sessionState === 'expired' ? undefined : 'Entre para operar Compras'"
        :description="sessionState === 'expired' ? undefined : 'Use uma conta autorizada a comprar e receber insumos.'"
      />
      <OperatorLock v-else-if="surface.showLock" :perm="OPERATOR_PERM" />
      <OperatorSonner />
      <OperatorPwaRuntime />
    </div>
  </OperatorAppRoot>
</template>
