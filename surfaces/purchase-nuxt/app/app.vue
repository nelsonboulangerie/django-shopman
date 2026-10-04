<script setup lang="ts">
const OPERATOR_PERM = "backstage.operate_purchase";
const { canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);
// Vincular o dispositivo a um posto (kit, a mesma regra dos oito apps): oferta, não
// parede, só para quem gere operadores, num dispositivo que ainda não é posto.
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });
const { view, selectMaterial, selectSupplier } = usePurchaseDesk();
const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;
const route = useRoute();

const SECTION_KEYS = ["panel", "buy", "receive", "base"] as const;

// Atalho do PWA ("Recebimento" → `/?view=receive`) e links diretos para uma seção.
function applyShortcutView(value: unknown) {
  if (typeof value === "string" && (SECTION_KEYS as readonly string[]).includes(value)) {
    view.value = value as typeof view.value;
  }
}
applyShortcutView(route.query.view);
watch(() => route.query.view, applyShortcutView);

// A busca da suíte abre um insumo ou um fornecedor na Base (`/?view=base&material=SKU`,
// `&supplier=REF`): o mesmo gesto do clique na lista.
function applyBaseLink(material: unknown, supplier: unknown) {
  if (typeof material === "string" && material) selectMaterial(material);
  else if (typeof supplier === "string" && supplier) selectSupplier(supplier);
}
applyBaseLink(route.query.material, route.query.supplier);
watch(() => [route.query.material, route.query.supplier], ([material, supplier]) => applyBaseLink(material, supplier));

useOperatorWindowTitle();
</script>

<template>
  <!-- `data-suite="v3"`: o Compras veste a camada visual da suíte (V4-COMPRAS, modelo do
       Gestor). Os primitivos do kit leem esse atributo para vestir o visual das prévias. -->
  <div class="flex min-h-dvh bg-background text-foreground" data-suite="v3">
    <NuxtRouteAnnouncer />
    <OfflineBanner />
    <!-- Rail da suíte (kit): o selo do app (Central), as quatro seções, avisos, Bloquear
         e o menu do operador. Do tablet para cima; no celular as seções vão para a barra
         do polegar, no fim da coluna de conteúdo. -->
    <PurchaseNav
      v-if="canIdentify"
      place="rail"
      :hub-url="hubUrl"
      :operator-name="operator?.name"
      @lock="lock"
    />
    <div class="flex min-w-0 flex-1 flex-col">
      <div v-show="canIdentify" class="flex min-h-0 min-w-0 flex-1 flex-col">
        <NuxtPage />
      </div>
      <PurchaseNav v-if="canIdentify && !locked && !mustChange" place="bar" :operator-name="operator?.name" @lock="lock" />
    </div>
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy do
         alpha subia a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="sessionUnavailable" scope="as compras" @retry="refresh()" />
    <OperatorLogin
      v-if="!canIdentify && !sessionUnavailable"
      title="Entre para operar Compras"
      description="Use uma conta autorizada a comprar e receber insumos."
    />
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
