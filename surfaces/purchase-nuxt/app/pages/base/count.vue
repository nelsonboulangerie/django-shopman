<script setup lang="ts">
// Base · Contagem: o que se contou no físico contra o que o sistema diz. Divergência
// pede motivo e vira ajuste no estoque, registrado com o operador. Só para quem tem a
// permissão de auditoria.
import { formatQty, formatQtyDiff } from "~/presentation/purchase";
import { plural } from "~/presentation/purchaseUi";

const {
  query,
  suppliers,
  metrics,
  countFilteredRows,
  countDivergentRows,
  countTotals,
  countReady,
  countPending,
  countForbidden,
  countConfirmedAt,
  setCountInput,
  setCountReason,
  resetCount,
  confirmCount,
  actionPending,
  refresh,
} = usePurchaseDesk();

type CountRow = (typeof countFilteredRows.value)[number];

const headerActions = [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];
const columns = [
  { id: "item", header: "Insumo", enableHiding: false },
  { id: "system", header: "Sistema", meta: { supporting: true } },
  { id: "counted", header: "Contado", enableHiding: false },
  { id: "diff", header: "Diferença", meta: { supporting: true } },
  { id: "reason", header: "Motivo", meta: { supporting: true } },
];

const confirmOpen = ref(false);
function openConfirm() {
  if (countReady.value) confirmOpen.value = true;
}
const submitting = ref(false);
async function submit() {
  submitting.value = true;
  try {
    if (await confirmCount()) confirmOpen.value = false;
  } finally {
    submitting.value = false;
  }
}

const summary = computed(() => {
  const parts = [
    plural(countTotals.value.filled, "contado", "contados"),
    plural(countTotals.value.divergent, "divergência", "divergências"),
  ];
  if (countTotals.value.missingReason) parts.push(`${countTotals.value.missingReason} sem motivo`);
  return parts.join(" · ");
});
const blockedReason = computed(() =>
  !countTotals.value.filled
    ? "Informe o que contou em pelo menos um insumo."
    : countTotals.value.missingReason
      ? `Falta o motivo de ${plural(countTotals.value.missingReason, "divergência", "divergências")}.`
      : "",
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Base" :actions="headerActions" actions-label="Mais ações da Base">
      <template #status>
        <PurchaseReadStatus />
      </template>
      <template #search>
        <OperatorSuiteSearch
          v-model="query"
          screen-label="filtrando a contagem"
          placeholder="Buscar insumo ou SKU"
          aria-label="Buscar insumo na contagem"
        />
      </template>
      <template #actions>
        <div v-if="!countForbidden" class="flex items-center gap-2 max-lg:hidden">
          <NuxtButton label="Limpar" color="neutral" variant="outline" :disabled="actionPending || !countTotals.filled" @click="resetCount()" />
          <NuxtButton
            icon="i-lucide-clipboard-check"
            label="Lançar contagem"
            :disabled="actionPending || countPending || !countReady"
            data-count-submit
            @click="openConfirm()"
          />
        </div>
      </template>
      <template #filters-primary>
        <PurchaseBaseSections :counts="{ materials: metrics.activeMaterials, suppliers: suppliers.length }" />
      </template>
      <template #filters-end>
        <span v-if="!countForbidden" class="text-xs text-muted tabular-nums">{{ summary }}</span>
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 space-y-3 overflow-auto p-4 sm:p-6" data-base-count>
      <PurchaseLoadState>
        <OperatorScreenState
          v-if="countForbidden"
          state="empty"
          icon="i-lucide-lock"
          title="Contagem restrita ao gestor."
          description="Auditar e ajustar o estoque de insumos pede a permissão de auditoria. Entre com o operador do gestor para contar."
        />
        <template v-else>
          <p class="text-sm text-muted">
            Informe o que contou no físico. Divergência pede motivo e vira ajuste no estoque.
            <span v-if="countConfirmedAt" class="text-success"> Última contagem lançada {{ countConfirmedAt }}.</span>
          </p>
          <OperatorTable
            :data="countFilteredRows"
            :columns="columns"
            :row-key="(row: CountRow) => row.item.sku"
            :row-label="(row: CountRow) => row.item.name"
            :loading="countPending"
            what="as posições do estoque"
            view-key="purchase-count"
            caption="Contagem de estoque"
            empty-icon="i-lucide-clipboard-check"
            :empty-title="query.trim() ? `Nenhum insumo com “${query.trim()}”.` : 'Nenhum insumo para contar.'"
            data-count-table
          >
            <template #item-cell="{ row }">
              <span class="block font-semibold">{{ row.original.item.name }}</span>
              <span class="block text-xs text-muted"><span class="font-mono">{{ row.original.item.sku }}</span> · {{ row.original.item.category }}</span>
              <!-- Celular: Sistema, Diferença e Motivo somem como colunas e moram aqui e
                   sob o campo do contado. -->
              <span class="block text-xs text-muted tabular-nums sm:hidden">Sistema: {{ formatQty(row.original.item.systemQty, row.original.item.unit) }}</span>
            </template>
            <template #system-cell="{ row }">
              <span class="whitespace-nowrap tabular-nums">{{ formatQty(row.original.item.systemQty, row.original.item.unit) }}</span>
            </template>
            <template #counted-cell="{ row }">
              <NuxtInput
                inputmode="decimal"
                :model-value="row.original.input"
                :placeholder="`0 ${row.original.item.unit}`"
                :aria-label="`Quantidade contada de ${row.original.item.name}`"
                :highlight="Boolean(row.original.input)"
                class="w-28 [&_input]:text-end [&_input]:tabular-nums"
                @update:model-value="(value: string | number) => setCountInput(row.original.item.sku, String(value ?? ''))"
              />
              <div v-if="row.original.counted !== null" class="mt-1 space-y-1 sm:hidden">
                <NuxtBadge
                  :color="row.original.divergent ? (row.original.diff < 0 ? 'error' : 'warning') : 'success'"
                  :label="row.original.divergent ? formatQtyDiff(row.original.diff, row.original.item.unit) : 'Confere'"
                  class="tabular-nums"
                />
                <NuxtInput
                  v-if="row.original.divergent"
                  :model-value="row.original.reason"
                  placeholder="Por que divergiu?"
                  :aria-label="`Motivo da divergência de ${row.original.item.name}`"
                  :color="row.original.missingReason ? 'error' : 'primary'"
                  :highlight="row.original.missingReason"
                  class="w-full"
                  @update:model-value="(value: string | number) => setCountReason(row.original.item.sku, String(value ?? ''))"
                />
              </div>
            </template>
            <template #diff-cell="{ row }">
              <NuxtBadge
                v-if="row.original.counted !== null"
                :color="row.original.divergent ? (row.original.diff < 0 ? 'error' : 'warning') : 'success'"
                :label="row.original.divergent ? formatQtyDiff(row.original.diff, row.original.item.unit) : 'Confere'"
                class="tabular-nums"
              />
              <span v-else class="text-xs text-muted">não contado</span>
            </template>
            <template #reason-cell="{ row }">
              <NuxtInput
                v-if="row.original.divergent"
                :model-value="row.original.reason"
                placeholder="Por que divergiu?"
                :aria-label="`Motivo da divergência de ${row.original.item.name}`"
                :color="row.original.missingReason ? 'error' : 'primary'"
                :highlight="row.original.missingReason"
                class="w-full min-w-40"
                @update:model-value="(value: string | number) => setCountReason(row.original.item.sku, String(value ?? ''))"
              />
              <span v-else class="text-xs text-muted">sem divergência</span>
            </template>
          </OperatorTable>
          <MoreBelow />
        </template>
      </PurchaseLoadState>
    </section>

    <OperatorActionBar
      v-if="!countForbidden && countTotals.filled"
      :action="{
        label: 'Lançar contagem',
        icon: 'i-lucide-clipboard-check',
        disabled: actionPending || countPending || !countReady,
        reason: blockedReason,
        onSelect: () => openConfirm(),
      }"
      :secondary="{ label: 'Limpar', onSelect: () => resetCount() }"
      context-label="Contagem"
      :context-value="summary"
    />

    <NuxtModal
      v-model:open="confirmOpen"
      title="Lançar a contagem no estoque?"
      description="Cada divergência vira um ajuste definitivo no livro de estoque, registrado com o seu usuário e o motivo informado."
    >
      <template #body>
        <ul v-if="countDivergentRows.length" class="max-h-64 space-y-2 overflow-y-auto">
          <li v-for="row in countDivergentRows" :key="row.item.sku">
            <NuxtCard variant="soft">
              <div class="flex items-center justify-between gap-2">
                <p class="text-sm font-semibold">{{ row.item.name }}</p>
                <span class="text-sm font-semibold tabular-nums" :class="row.diff < 0 ? 'text-error' : 'text-warning'">{{ formatQtyDiff(row.diff, row.item.unit) }}</span>
              </div>
              <p class="text-xs text-muted tabular-nums">
                {{ formatQty(row.item.systemQty, row.item.unit) }} no sistema · {{ formatQty(row.counted ?? 0, row.item.unit) }} contado
              </p>
              <p class="mt-1 text-xs">{{ row.reason }}</p>
            </NuxtCard>
          </li>
        </ul>
        <NuxtAlert
          v-else
          variant="subtle"
          color="success"
          title="Sem divergência: a contagem confirma o saldo do sistema e nenhum ajuste será lançado."
        />
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton label="Voltar" color="neutral" variant="outline" :disabled="submitting" @click="confirmOpen = false" />
          <NuxtButton
            icon="i-lucide-check"
            :label="countDivergentRows.length ? 'Lançar os ajustes' : 'Confirmar a contagem'"
            :color="countDivergentRows.length ? 'error' : 'primary'"
            :loading="submitting"
            data-count-confirm
            @click="submit()"
          />
        </div>
      </template>
    </NuxtModal>
  </main>
</template>
