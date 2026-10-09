<script setup lang="ts">
// Base · Custos: a tabela de preços de um fornecedor (lançar vários custos de uma vez,
// o gesto que tira dezenas de insumos do estado "sem custo preferencial"), o custo
// avulso e os custos de cada fornecedor por insumo.
import type { EnrichedMaterial, SupplierMaterialCost } from "~/types/purchase";
import { costPerBaseUnitQ, formatMoney, isApproximateCost, purchaseUnitLabel } from "~/presentation/purchase";
import { plural } from "~/presentation/purchaseUi";

const {
  materials,
  suppliers,
  conversions,
  costs,
  metrics,
  batchSupplierRef,
  batchInputs,
  batchConversionIds,
  batchOnlyMissing,
  batchQuery,
  batchLineErrors,
  batchRows,
  batchFilledCount,
  batchReady,
  batchConversionsFor,
  setBatchInput,
  setBatchConversion,
  clearCostBatch,
  saveCostBatch,
  noteMaterialSku,
  noteSupplierRef,
  noteConversionId,
  noteCostInput,
  availableNoteConversions,
  notePreview,
  readonlyFallback,
  actionPending,
  setPreferredCost,
  saveQuote,
  refresh,
} = usePurchaseDesk();

const headerActions = [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];

// Fornecedor inativo não recebe custo preferencial (a casa recusa): não oferecer é
// melhor que recusar.
const activeSupplierItems = computed(() =>
  suppliers.value.filter((supplier) => supplier.isActive).map((supplier) => ({ label: supplier.displayName, value: supplier.ref })),
);
const supplierItems = computed(() => suppliers.value.map((supplier) => ({ label: supplier.displayName, value: supplier.ref })));
const materialItems = computed(() => materials.value.map((material) => ({ label: material.name, value: material.sku })));
// `NuxtSelect` não aceita valor vazio num item: a unidade-base vai como sentinela e
// volta vazia para o rascunho (sem conversão).
const BASE_UNIT = "__base__";
const noteConversionModel = computed({
  get: () => noteConversionId.value || BASE_UNIT,
  set: (value: string) => (noteConversionId.value = value === BASE_UNIT ? "" : value),
});
const noteConversionItems = computed(() => [
  { label: "Unidade-base", value: BASE_UNIT },
  ...availableNoteConversions.value.map((conversion) => ({ label: conversion.label, value: conversion.id })),
]);
function batchConversionItems(row: EnrichedMaterial) {
  return [
    { label: `Unidade-base (${row.unit})`, value: BASE_UNIT },
    ...batchConversionsFor(row.sku).map((conversion) => ({ label: conversion.label, value: conversion.id })),
  ];
}

const touch = useCoarsePointer();

const batchColumns = [
  { id: "material", header: "Insumo", enableHiding: false },
  { id: "unit", header: "Unidade de compra", meta: { supporting: true } },
  { id: "value", header: "Valor", enableHiding: false },
];
const costColumns = [
  { id: "material", header: "Insumo", enableHiding: false },
  { id: "supplier", header: "Fornecedor" },
  { id: "purchase", header: "Compra", meta: { supporting: true } },
  { id: "base", header: "Custo-base" },
  { id: "preferred", header: "Padrão", enableHiding: false },
];
const materialName = (sku: string) => materials.value.find((material) => material.sku === sku)?.name ?? sku;
const supplierName = (ref: string) => suppliers.value.find((supplier) => supplier.ref === ref)?.displayName ?? ref;

const batchEmptyTitle = computed(() => {
  if (!materials.value.length) return "Nenhum insumo cadastrado na Base.";
  if (batchQuery.value.trim()) return `Nenhum insumo com “${batchQuery.value.trim()}”.`;
  if (batchOnlyMissing.value) return "Todo insumo ativo já tem custo preferencial.";
  return "Nenhum insumo ativo na Base.";
});

const quoteDisabled = computed(() => !notePreview.value || !noteMaterialSku.value || !noteSupplierRef.value);
const savingBatch = ref(false);
async function onSaveBatch() {
  savingBatch.value = true;
  try {
    await saveCostBatch();
  } finally {
    savingBatch.value = false;
  }
}
const savingQuote = ref<"" | "plain" | "preferred">("");
async function onSaveQuote(preferred: boolean) {
  savingQuote.value = preferred ? "preferred" : "plain";
  try {
    await saveQuote(preferred);
  } finally {
    savingQuote.value = "";
  }
}
const preferringId = ref("");
async function onPrefer(cost: SupplierMaterialCost) {
  preferringId.value = cost.id;
  try {
    await setPreferredCost(cost.id);
  } finally {
    preferringId.value = "";
  }
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Base" :actions="headerActions" actions-label="Mais ações da Base">
      <template #status>
        <PurchaseReadStatus />
      </template>
      <template #search>
        <OperatorSuiteSearch
          v-model="batchQuery"
          screen-label="filtrando a tabela do fornecedor"
          placeholder="Buscar insumo na tabela"
          aria-label="Buscar insumo na tabela do fornecedor"
        />
      </template>
      <template #filters-primary>
        <PurchaseBaseSections current="costs" :counts="{ materials: metrics.activeMaterials, suppliers: suppliers.length }" />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 space-y-6 overflow-auto p-4 sm:p-6" data-base-costs>
      <PurchaseLoadState>
        <section class="space-y-3" aria-labelledby="batch-title" data-cost-batch>
          <div>
            <h2 id="batch-title" class="text-base font-semibold">Tabela do fornecedor</h2>
            <p class="text-sm text-muted">Escolha o fornecedor e preencha os valores que você sabe. Quem ficar em branco não entra.</p>
          </div>
          <div class="flex flex-wrap items-end gap-2">
            <NuxtFormField label="Fornecedor" class="w-full sm:w-64">
              <NuxtSelectMenu
                v-model="batchSupplierRef"
                :items="activeSupplierItems"
                value-key="value"
                placeholder="Escolher o fornecedor"
                :search-input="{ autofocus: !touch, placeholder: 'Buscar fornecedor' }"
                class="w-full"
                data-cost-batch-supplier
              />
            </NuxtFormField>
            <NuxtButton
              icon="i-lucide-badge-alert"
              label="Só os sem custo preferencial"
              color="neutral"
              variant="outline"
              :active="batchOnlyMissing"
              active-variant="soft"
              active-color="primary"
              :aria-pressed="batchOnlyMissing"
              @click="batchOnlyMissing = !batchOnlyMissing"
            />
          </div>
          <OperatorTable
            :data="batchRows"
            :columns="batchColumns"
            :row-key="(row: EnrichedMaterial) => row.sku"
            :row-label="(row: EnrichedMaterial) => row.name"
            caption="Tabela de preços do fornecedor"
            empty-icon="i-lucide-calculator"
            :empty-title="batchEmptyTitle"
            data-cost-batch-table
          >
            <template #material-cell="{ row }">
              <span class="block font-semibold">{{ row.original.name }}</span>
              <span class="block text-xs text-muted"><span class="font-mono">{{ row.original.sku }}</span> · {{ row.original.unit }}</span>
              <span v-if="batchLineErrors[row.original.sku]" class="block text-xs font-semibold text-error">{{ batchLineErrors[row.original.sku] }}</span>
              <!-- Celular: a unidade de compra desce para baixo do nome (a coluna some). -->
              <NuxtSelect
                :model-value="batchConversionIds[row.original.sku] || BASE_UNIT"
                :items="batchConversionItems(row.original)"
                value-key="value"
                :aria-label="`Unidade de compra de ${row.original.name}`"
                class="mt-1 w-full sm:hidden"
                @update:model-value="(value: unknown) => setBatchConversion(row.original.sku, value === BASE_UNIT ? '' : String(value ?? ''))"
              />
            </template>
            <template #unit-cell="{ row }">
              <NuxtSelect
                :model-value="batchConversionIds[row.original.sku] || BASE_UNIT"
                :items="batchConversionItems(row.original)"
                value-key="value"
                :aria-label="`Unidade de compra de ${row.original.name}`"
                class="w-full min-w-36"
                @update:model-value="(value: unknown) => setBatchConversion(row.original.sku, value === BASE_UNIT ? '' : String(value ?? ''))"
              />
            </template>
            <template #value-cell="{ row }">
              <NuxtInput
                inputmode="decimal"
                placeholder="0,00"
                :aria-label="`Valor de ${row.original.name}`"
                :model-value="batchInputs[row.original.sku] ?? ''"
                :color="batchLineErrors[row.original.sku] ? 'error' : 'primary'"
                :highlight="Boolean(batchLineErrors[row.original.sku] || batchInputs[row.original.sku])"
                class="w-24 sm:w-28 [&_input]:text-end [&_input]:tabular-nums"
                @update:model-value="(value: string | number) => setBatchInput(row.original.sku, String(value ?? ''))"
              />
            </template>
            <template #footer>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <p class="text-sm">
                  <template v-if="!batchSupplierRef">Escolha o fornecedor para lançar.</template>
                  <template v-else><span class="font-semibold tabular-nums">{{ plural(batchFilledCount, "valor preenchido", "valores preenchidos") }}</span></template>
                </p>
                <div class="flex gap-2">
                  <NuxtButton label="Limpar" color="neutral" variant="outline" :disabled="!batchFilledCount || actionPending" @click="clearCostBatch()" />
                  <NuxtButton
                    icon="i-lucide-check"
                    :label="batchFilledCount ? `Salvar ${batchFilledCount} como padrão` : 'Salvar como padrão'"
                    :loading="savingBatch"
                    :disabled="readonlyFallback || !batchReady || actionPending"
                    data-cost-batch-save
                    @click="onSaveBatch()"
                  />
                </div>
              </div>
            </template>
          </OperatorTable>
        </section>

        <div class="grid grid-cols-1 gap-6 xl:grid-cols-[22rem_minmax(0,1fr)]">
          <section aria-labelledby="quote-title" data-cost-quote>
            <NuxtCard>
              <h2 id="quote-title" class="text-base font-semibold">Lançar um custo</h2>
              <div class="mt-3 space-y-3">
                <NuxtFormField label="Insumo">
                  <NuxtSelectMenu
                    v-model="noteMaterialSku"
                    :items="materialItems"
                    value-key="value"
                    placeholder="Escolher o insumo"
                    :search-input="{ autofocus: !touch, placeholder: 'Buscar insumo' }"
                    class="w-full"
                  />
                </NuxtFormField>
                <NuxtFormField label="Fornecedor">
                  <NuxtSelectMenu
                    v-model="noteSupplierRef"
                    :items="supplierItems"
                    value-key="value"
                    placeholder="Escolher o fornecedor"
                    :search-input="{ autofocus: !touch, placeholder: 'Buscar fornecedor' }"
                    class="w-full"
                  />
                </NuxtFormField>
                <NuxtFormField label="Unidade de compra">
                  <NuxtSelect v-model="noteConversionModel" :items="noteConversionItems" value-key="value" class="w-full" />
                </NuxtFormField>
                <NuxtFormField label="Valor da unidade de compra">
                  <NuxtInput v-model="noteCostInput" inputmode="decimal" placeholder="180,00" class="w-full [&_input]:tabular-nums" />
                </NuxtFormField>
                <NuxtCard variant="soft">
                  <p class="text-xs text-muted">Custo por unidade-base</p>
                  <p class="text-2xl font-semibold tabular-nums">
                    <template v-if="notePreview"><span v-if="notePreview.approximate">≈ </span>{{ formatMoney(notePreview.baseCostQ) }}</template>
                    <template v-else>R$ 0,00</template>
                  </p>
                </NuxtCard>
                <div class="grid grid-cols-2 gap-2">
                  <NuxtButton
                    label="Salvar custo"
                    color="neutral"
                    variant="outline"
                    block
                    :loading="savingQuote === 'plain'"
                    :disabled="readonlyFallback || quoteDisabled || actionPending"
                    @click="onSaveQuote(false)"
                  />
                  <NuxtButton
                    label="Salvar como padrão"
                    block
                    :loading="savingQuote === 'preferred'"
                    :disabled="readonlyFallback || quoteDisabled || actionPending"
                    @click="onSaveQuote(true)"
                  />
                </div>
              </div>
            </NuxtCard>
          </section>

          <section class="min-w-0 space-y-3" aria-labelledby="costs-title" data-cost-list>
            <h2 id="costs-title" class="text-base font-semibold">Custos por fornecedor</h2>
            <OperatorTable
              :data="costs"
              :columns="costColumns"
              :row-key="(row: SupplierMaterialCost) => row.id"
              :row-label="(row: SupplierMaterialCost) => `${materialName(row.materialSku)} de ${supplierName(row.supplierRef)}`"
              view-key="purchase-costs"
              caption="Custos por fornecedor"
              empty-icon="i-lucide-calculator"
              empty-title="Nenhum custo lançado ainda."
            >
              <template #material-cell="{ row }">
                <span class="font-semibold">{{ materialName(row.original.materialSku) }}</span>
              </template>
              <template #supplier-cell="{ row }">
                {{ supplierName(row.original.supplierRef) }}
              </template>
              <template #purchase-cell="{ row }">
                <span class="whitespace-nowrap tabular-nums">
                  {{ formatMoney(row.original.costQ) }} / {{ purchaseUnitLabel(row.original, materials.find((material) => material.sku === row.original.materialSku), conversions) }}
                </span>
              </template>
              <template #base-cell="{ row }">
                <span class="whitespace-nowrap font-semibold tabular-nums">
                  <span v-if="isApproximateCost(row.original, conversions)">≈ </span>{{ formatMoney(costPerBaseUnitQ(row.original, conversions)) }}
                </span>
              </template>
              <template #preferred-cell="{ row }">
                <NuxtBadge v-if="row.original.isPreferred" color="success" icon="i-lucide-check" label="Padrão" />
                <NuxtButton
                  v-else
                  label="Usar como padrão"
                  color="neutral"
                  variant="outline"
                  :loading="preferringId === row.original.id"
                  :disabled="readonlyFallback || actionPending"
                  @click="onPrefer(row.original)"
                />
              </template>
            </OperatorTable>
          </section>
        </div>
      </PurchaseLoadState>
    </section>
  </main>
</template>
