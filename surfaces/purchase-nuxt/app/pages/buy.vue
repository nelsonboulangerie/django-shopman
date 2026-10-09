<script setup lang="ts">
// Comprar: a fila de reposição (o que o estoque, a produção e a operação pedem), um
// cartão por insumo, com o fornecedor, a sugestão e o gesto de enviar o pedido.
import type { EnrichedMaterial } from "~/types/purchase";
import { coverageLabel, formatMoney, purchaseSuggestionLabel } from "~/presentation/purchase";
import { baseSectionPath } from "~/presentation/purchaseSections";
import { REQUEST_BADGE, REQUEST_LABEL, plural } from "~/presentation/purchaseUi";

const {
  reorderRows,
  reorderBlockers,
  readonlyFallback,
  actionPending,
  purchaseRequestStatus,
  sendPurchaseRequest,
  selectMaterial,
  noteMaterialSku,
  noteSupplierRef,
  refresh,
} = usePurchaseDesk();

const purchaseTotalQ = computed(() => reorderRows.value.reduce((total, row) => total + (row.estimatedCostQ ?? 0), 0));
const supplierCount = computed(() => new Set(reorderRows.value.map((row) => row.supplier?.ref).filter(Boolean)).size);

const headerActions = [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];

// A fila vazia explicada: sem isto, "não precisa comprar nada" e "o app não consegue
// calcular" seriam a mesma tela vazia. Cada aviso leva ao cadastro que destrava.
const blockerAlerts = computed(() =>
  reorderRows.value.length
    ? []
    : reorderBlockers.value
        .filter((blocker) => blocker.action)
        .map((blocker) => ({
          id: blocker.key,
          color: "info" as const,
          title: blocker.headline,
          description: blocker.detail,
          action: blocker.action ? { label: blocker.action.label, to: baseSectionPath(blocker.action.baseView) } : undefined,
        })),
);
const stocked = computed(() => reorderBlockers.value.find((blocker) => blocker.key === "stocked") ?? null);

function openQuoteFor(material: EnrichedMaterial, supplierRef?: string) {
  selectMaterial(material.sku);
  noteMaterialSku.value = material.sku;
  if (supplierRef) noteSupplierRef.value = supplierRef;
  void navigateTo(baseSectionPath("costs"));
}

const sendingSku = ref("");
async function send(sku: string) {
  sendingSku.value = sku;
  try {
    await sendPurchaseRequest(sku);
  } finally {
    sendingSku.value = "";
  }
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Comprar" :actions="headerActions" actions-label="Mais ações de Comprar" :alerts="blockerAlerts">
      <template #status>
        <PurchaseReadStatus />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6" data-purchase-buy>
      <PurchaseLoadState>
        <OperatorScreenState
          v-if="!reorderRows.length"
          state="empty"
          icon="i-lucide-circle-check"
          title="Nada para comprar agora."
          :description="stocked?.detail ?? 'Os avisos acima dizem o que falta para o Compras calcular a reposição.'"
        />
        <div v-else class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <div class="grid min-w-0 content-start gap-3 md:grid-cols-2 2xl:grid-cols-3" role="list" aria-label="Insumos para comprar">
            <NuxtCard v-for="row in reorderRows" :key="row.material.sku" role="listitem" :data-buy-row="row.material.sku">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h2 class="text-base font-semibold">{{ row.material.name }}</h2>
                  <p class="text-xs text-muted"><span class="font-mono">{{ row.material.sku }}</span> · {{ row.material.category }}</p>
                </div>
                <NuxtBadge
                  :color="REQUEST_BADGE[purchaseRequestStatus(row.material.sku)]"
                  :label="REQUEST_LABEL[purchaseRequestStatus(row.material.sku)]"
                  class="shrink-0"
                />
              </div>
              <dl class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                <div class="col-span-2"><dt class="text-xs text-muted">Cobertura</dt><dd class="font-semibold tabular-nums">{{ coverageLabel(row.material.coverageDays) }}</dd></div>
                <div class="col-span-2"><dt class="text-xs text-muted">Comprar</dt><dd class="font-semibold tabular-nums">{{ purchaseSuggestionLabel(row.material, row.suggestedQty) }}</dd></div>
                <div class="min-w-0"><dt class="text-xs text-muted">Fornecedor</dt><dd class="font-semibold">{{ row.supplier?.displayName || row.supplier?.name || "Sem fornecedor" }}</dd></div>
                <div><dt class="text-xs text-muted">Estimado</dt><dd class="font-semibold tabular-nums">{{ row.estimatedCostQ == null ? "sem custo" : formatMoney(row.estimatedCostQ) }}</dd></div>
              </dl>
              <div class="mt-3 grid grid-cols-2 gap-2">
                <NuxtButton
                  label="Lançar custo"
                  color="neutral"
                  variant="outline"
                  block
                  @click="openQuoteFor(row.material, row.supplier?.ref)"
                />
                <NuxtButton
                  :label="purchaseRequestStatus(row.material.sku) === 'sent' ? 'Pedido enviado' : 'Enviar pedido'"
                  block
                  :loading="sendingSku === row.material.sku"
                  :disabled="readonlyFallback || purchaseRequestStatus(row.material.sku) === 'sent' || actionPending"
                  @click="send(row.material.sku)"
                />
              </div>
            </NuxtCard>
          </div>

          <NuxtCard class="h-fit" data-buy-summary>
            <h2 class="text-base font-semibold">Consolidação</h2>
            <dl class="mt-3 grid grid-cols-2 gap-3">
              <div><dt class="text-xs text-muted">Insumos</dt><dd class="text-2xl font-semibold tabular-nums">{{ reorderRows.length }}</dd></div>
              <div><dt class="text-xs text-muted">Fornecedores</dt><dd class="text-2xl font-semibold tabular-nums">{{ supplierCount }}</dd></div>
              <div class="col-span-2"><dt class="text-xs text-muted">Total previsto</dt><dd class="text-2xl font-semibold tabular-nums">{{ formatMoney(purchaseTotalQ) }}</dd></div>
            </dl>
            <div class="mt-3 grid gap-2">
              <NuxtButton :to="baseSectionPath('suppliers')" icon="i-lucide-truck" label="Fornecedores" color="neutral" variant="outline" block />
              <NuxtButton :to="baseSectionPath('costs')" icon="i-lucide-calculator" label="Custos e embalagens" color="neutral" variant="outline" block />
            </div>
            <p class="mt-3 text-xs text-muted">{{ plural(reorderRows.length, "insumo", "insumos") }} abaixo do ponto de reposição, pelo consumo e pelo mínimo.</p>
          </NuxtCard>
        </div>
      </PurchaseLoadState>
    </section>
  </main>
</template>
