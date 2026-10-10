<script setup lang="ts">
// Painel do Compras: o que precisa de alguém agora (comprar, receber, cadastro com
// falta) e o atalho para o gesto mais comum, receber uma NF. Cada linha leva aonde o
// gesto se faz.
import { coverageLabel, formatMoney, purchaseSuggestionLabel } from "~/presentation/purchase";
import { baseSectionPath } from "~/presentation/purchaseSections";
import { TONE_BADGE, TONE_LABEL, plural } from "~/presentation/purchaseUi";

const {
  metrics,
  reorderRows,
  reorderBlockers,
  integrityQueue,
  receiptConference,
  receiptIsBlank,
  receiptReady,
  receiptTotalPending,
  refresh,
} = usePurchaseDesk();

const purchaseTotalQ = computed(() => reorderRows.value.reduce((total, row) => total + (row.estimatedCostQ ?? 0), 0));

const headerActions = [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];

// Os quatro números do dia, cada um levando à tela onde se age sobre ele.
const tiles = computed(() => [
  {
    key: "buy",
    to: "/buy",
    icon: "i-lucide-shopping-cart",
    title: plural(reorderRows.value.length, "insumo para comprar", "insumos para comprar"),
    description: reorderRows.value.length ? `${formatMoney(purchaseTotalQ.value)} estimados` : "Nada abaixo do ponto de reposição",
  },
  {
    key: "receive",
    to: "/receive",
    icon: "i-lucide-package-check",
    title: receiptIsBlank.value
      ? "Nenhuma entrada em conferência"
      : `${receiptConference.value.ready} de ${plural(receiptConference.value.total, "item conferido", "itens conferidos")}`,
    description: receiptIsBlank.value
      ? "Escaneie a NF para começar"
      : receiptTotalPending.value
        ? plural(receiptTotalPending.value, "pendência na entrada", "pendências na entrada")
        : "Pronta para confirmar",
  },
  {
    key: "costs",
    to: baseSectionPath("costs"),
    icon: "i-lucide-equal-approximately",
    title: plural(metrics.value.approximatePreferred, "custo estimado", "custos estimados"),
    description: "Custo preferencial por uma embalagem de peso estimado",
  },
  {
    key: "base",
    to: baseSectionPath("materials"),
    icon: "i-lucide-database",
    title: plural(metrics.value.activeMaterials, "insumo ativo", "insumos ativos"),
    description: `${metrics.value.missingPreferred} sem custo preferencial`,
  },
]);

// "Precisa de você": o que pede gesto agora, na ordem em que se resolve.
const needsYou = computed(() => [
  ...reorderRows.value.slice(0, 5).map((row) => ({
    key: `buy-${row.material.sku}`,
    to: "/buy",
    title: row.material.name,
    detail: `${coverageLabel(row.material.coverageDays)} · comprar ${purchaseSuggestionLabel(row.material, row.suggestedQty)}`,
    badge: { label: "Comprar", color: "error" as const },
  })),
  ...(receiptIsBlank.value
    ? []
    : [
        {
          key: "receive",
          to: "/receive",
          title: "Entrada em conferência",
          detail: receiptConference.value.label,
          badge: receiptReady.value
            ? { label: "Pronta", color: "success" as const }
            : { label: "Revisar", color: "warning" as const },
        },
      ]),
  // O insumo que já está na fila de compra não repete pela falta de cadastro.
  ...integrityQueue.value
    .filter((item) => !reorderRows.value.slice(0, 5).some((row) => row.material.sku === item.material.sku))
    .slice(0, 4)
    .map((item) => ({
    key: `integrity-${item.material.sku}-${item.issue.key}`,
    to: `/base/materials/${encodeURIComponent(item.material.sku)}`,
    title: item.material.name,
    detail: item.issue.label,
    badge: { label: TONE_LABEL[item.issue.tone], color: TONE_BADGE[item.issue.tone] },
  })),
]);

// A fila vazia diz o motivo onde o olho está: sem consumo medido, sem custo padrão.
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
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Painel" :actions="headerActions" actions-label="Mais ações do Painel" :alerts="blockerAlerts">
      <template #status>
        <PurchaseReadStatus />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6" data-purchase-panel>
      <PurchaseLoadState>
        <div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div class="min-w-0 space-y-4">
            <NuxtCard data-panel-needs-you>
              <h2 class="text-base font-semibold">Precisa de você</h2>
              <ul v-if="needsYou.length" class="mt-2 divide-y divide-default">
                <li v-for="item in needsYou" :key="item.key">
                  <NuxtLink
                    :to="item.to"
                    class="flex min-h-12 items-center justify-between gap-3 py-2 hover:text-highlighted"
                    :data-panel-item="item.key"
                  >
                    <span class="min-w-0">
                      <span class="block text-sm font-semibold">{{ item.title }}</span>
                      <span class="block text-xs text-muted">{{ item.detail }}</span>
                    </span>
                    <NuxtBadge :color="item.badge.color" :label="item.badge.label" class="shrink-0" />
                  </NuxtLink>
                </li>
              </ul>
              <OperatorScreenState
                v-else
                state="empty"
                in-card
                icon="i-lucide-circle-check"
                title="Nada precisa de você agora."
                :description="reorderBlockers[0]?.key === 'stocked' ? reorderBlockers[0].detail : ''"
              />
            </NuxtCard>
            <div class="grid grid-cols-2 gap-3 2xl:grid-cols-4" aria-label="Compras hoje" role="list">
              <NuxtPageCard
                v-for="tile in tiles"
                :key="tile.key"
                :to="tile.to"
                :icon="tile.icon"
                :title="tile.title"
                :description="tile.description"
                role="listitem"
                :data-panel-tile="tile.key"
              />
            </div>

          </div>

          <!-- O gesto mais comum do Compras: receber uma NF. Na mesa, aqui; no celular, na
               ação da base. -->
          <aside class="space-y-2" aria-label="Atalhos do Compras">
            <NuxtButton
              to="/receive?scan=1"
              size="xl"
              icon="i-lucide-scan-line"
              label="Escanear NF"
              block
              class="max-lg:hidden"
              data-panel-scan
            />
            <div class="grid grid-cols-2 gap-2">
              <NuxtButton to="/receive?key=1" icon="i-lucide-keyboard" label="Digitar chave" color="neutral" variant="outline" block />
              <NuxtButton to="/receive?manual=1" icon="i-lucide-clipboard-pen-line" label="Sem NF" color="neutral" variant="outline" block />
            </div>
            <NuxtButton to="/buy" icon="i-lucide-shopping-cart" label="Revisar compras" color="neutral" variant="ghost" block />
            <NuxtButton :to="baseSectionPath('materials')" icon="i-lucide-database" label="Consultar a Base" color="neutral" variant="ghost" block />
          </aside>
        </div>
      </PurchaseLoadState>
    </section>

    <OperatorActionBar
      :action="{ label: 'Escanear NF', icon: 'i-lucide-scan-line', onSelect: () => void navigateTo('/receive?scan=1') }"
    />
  </main>
</template>
