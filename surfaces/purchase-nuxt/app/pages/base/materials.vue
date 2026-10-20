<script setup lang="ts">
// Base · Insumos: a tabela da suíte (`OperatorTable`) e o mínimo de cada insumo editável
// na linha. O insumo aberto é a rota filha (`/base/materials/<sku>`, `materials/[sku].vue`):
// a tabela fica montada enquanto o detalhe abre ao lado e "‹ 3 de 18 ›" anda dentro da
// lista que a pessoa via (o recorte e a ordem dela).
import type { EnrichedMaterial } from "~/types/purchase";
import { coverageLabel, formatMoney, formatQty, formatStockOnHand, skuRoleBadges } from "~/presentation/purchase";
import { MATERIALS_TRAIL, baseSectionPath, materialPath, urgentLabel } from "~/presentation/purchaseSections";
import {
  MATERIAL_ATTENTION_TONES,
  TONE_BADGE,
  TONE_LABEL,
  TONE_RANK,
  isAttentionRecorte,
  materialDimensions,
  plural,
} from "~/presentation/purchaseUi";
import { filterBarActiveFilters } from "../../../../operator-kit/app/presentation/filterBar";

const csvTools = ref<{ openImport: () => void; openExport: () => void } | null>(null);
const route = useRoute();
const {
  query,
  materialFilters,
  materials,
  materialList,
  supplierList,
  suppliers,
  enrichedMaterials,
  filteredMaterials,
  metrics,
  minStockInputs,
  minStockLineErrors,
  minStockFilledCount,
  setMinStockInput,
  clearMinStock,
  saveMinStock,
  batchOnlyMissing,
  selectMaterial,
  readonlyFallback,
  actionPending,
  actionError,
  materialForm,
  materialFormSource,
  materialFormConversions,
  materialFormCosts,
  materialCategories,
  openMaterialCreate,
  saveMaterial,
  saveMaterialConversion,
  saveMaterialCost,
  refresh,
} = usePurchaseDesk();

const openSku = computed(() => (typeof route.params.sku === "string" ? route.params.sku : ""));
watch(openSku, (sku) => {
  if (sku) selectMaterial(sku);
}, { immediate: true });

function openMaterial(material: EnrichedMaterial) {
  void navigateTo(materialPath(material.sku));
}

const sorting = ref<{ id: string; desc: boolean }[]>([]);
watch(sorting, (value) => {
  const sort = value[0];
  const order = sort?.id === "name" ? (sort.desc ? "-name" : "name") : "name";
  void navigateTo({ query: { ...route.query, order, page: "1" } }, { replace: true });
}, { deep: true });
function goToPage(page: number) {
  void navigateTo({ query: { ...route.query, page: String(page) } }, { replace: true });
}
const SORT_VALUE: Record<string, (material: EnrichedMaterial) => number | string> = {
  name: (material) => material.name,
  stock: (material) => material.stockOnHand,
  coverage: (material) => material.coverageDays,
  cost: (material) => material.preferredBaseCostQ ?? Number.POSITIVE_INFINITY,
  tone: (material) => TONE_RANK[material.tone],
};
// Com o insumo aberto ao lado, a tabela encolhe e solta Cobertura e Custo-base antes de
// rolar de lado (regra de precedência da fase 2).
const yieldsToDetail = computed(() => (openSku.value ? { th: "max-2xl:hidden", td: "max-2xl:hidden" } : undefined));
const columns = computed(() => [
  { id: "name", header: "Insumo", accessorFn: SORT_VALUE.name, enableSorting: true, enableHiding: false },
  { id: "stock", header: "Estoque", accessorFn: SORT_VALUE.stock },
  { id: "coverage", header: "Cobertura", accessorFn: SORT_VALUE.coverage, meta: { supporting: true, class: yieldsToDetail.value } },
  { id: "minimum", header: "Mínimo", enableHiding: false },
  { id: "cost", header: "Custo-base", accessorFn: SORT_VALUE.cost, meta: { supporting: true, class: yieldsToDetail.value } },
  { id: "tone", header: "Situação", accessorFn: SORT_VALUE.tone, meta: { supporting: true } },
]);

// A ordem que a tabela mostra: é a trilha do "‹ 3 de 18 ›" do insumo aberto.
const displayed = computed(() => filteredMaterials.value);
const { remember } = useRecordTrail(MATERIALS_TRAIL);
watch(
  displayed,
  (list) => remember(list.map((material) => material.sku), { from: baseSectionPath("materials"), label: "Insumos" }),
  { immediate: true },
);

// O painel de filtros único da suíte (Situação e Categoria, com os favoritos da pessoa)
// e, na mesa, o filtro rápido "Pedem atenção" (a Situação em Comprar ou Revisar).
const dimensions = computed(() => materialDimensions(enrichedMaterials.value));
const quickItems = computed(() => [
  {
    key: "attention",
    label: "Pedem atenção",
    icon: "i-lucide-triangle-alert",
    count: enrichedMaterials.value.filter((material) => material.tone !== "ok").length,
  },
]);
const quickModel = computed<string[]>({
  get: () => (isAttentionRecorte(materialFilters.value) ? ["attention"] : []),
  set: (keys) => {
    const next = { ...materialFilters.value };
    delete next.tone;
    if (keys.includes("attention")) next.tone = [...MATERIAL_ATTENTION_TONES];
    materialFilters.value = next;
  },
});
// Os chips do cabeçalho no celular (na mesa, os do painel, ao lado do botão).
const activeFilters = computed(() =>
  filterBarActiveFilters(dimensions.value, materialFilters.value, (next) => {
    materialFilters.value = next;
  }),
);

// O que a Base precisa que a pessoa saiba agora, cada aviso levando aonde se resolve.
const alerts = computed(() => {
  const list = [];
  if (metrics.value.urgentMaterials) {
    list.push({
      id: "urgent",
      color: "warning" as const,
      title: urgentLabel(metrics.value.urgentMaterials),
      description: "Estoque abaixo do ponto de reposição.",
      action: { label: "Ver em Comprar", to: "/buy" },
    });
  }
  if (metrics.value.missingPreferred) {
    list.push({
      id: "missing-preferred",
      color: "info" as const,
      title: `${plural(metrics.value.missingPreferred, "insumo", "insumos")} sem custo preferencial`,
      description: "Sem custo preferencial o insumo fica fora de qualquer pedido de compra.",
      action: {
        label: "Lançar os custos",
        onSelect: () => {
          batchOnlyMissing.value = true;
          void navigateTo(baseSectionPath("costs"));
        },
      },
    });
  }
  if (metrics.value.approximatePreferred) {
    list.push({
      id: "approximate",
      color: "info" as const,
      title: plural(metrics.value.approximatePreferred, "custo estimado", "custos estimados"),
      description: "O custo preferencial passa por uma embalagem de peso estimado.",
      action: { label: "Ver os custos", to: baseSectionPath("costs") },
    });
  }
  return list;
});

const headerActions = [
  { label: "Importar CSV", icon: "i-lucide-upload", onSelect: () => csvTools.value?.openImport() },
  { label: "Exportar CSV", icon: "i-lucide-download", onSelect: () => csvTools.value?.openExport() },
  { label: "Novo insumo", icon: "i-lucide-plus", onSelect: () => openMaterialCreate() },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
  { label: "Contagem de estoque", icon: "i-lucide-clipboard-check", to: baseSectionPath("count") },
];

async function onSubmitMaterial(payload: Record<string, unknown>) {
  const sku = await saveMaterial(payload);
  if (sku) await navigateTo(materialPath(sku));
}

const materialSavedVersion = ref(0);
async function onSaveMaterialConversion(payload: Parameters<typeof saveMaterialConversion>[0]) {
  if (await saveMaterialConversion(payload)) materialSavedVersion.value += 1;
}
async function onSaveMaterialCost(payload: Parameters<typeof saveMaterialCost>[0]) {
  if (await saveMaterialCost(payload)) materialSavedVersion.value += 1;
}

const saving = ref(false);
async function onSaveMinStock() {
  saving.value = true;
  try {
    await saveMinStock();
  } finally {
    saving.value = false;
  }
}
const saveLabel = computed(() =>
  `Salvar ${plural(minStockFilledCount.value, "mínimo", "mínimos")}`,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Base"
      :actions="headerActions"
      actions-label="Mais ações da Base"
      :alerts="alerts"
      :active-filters="activeFilters"
      desk-only-filters
    >
      <template #status>
        <PurchaseReadStatus />
      </template>
      <template #search>
        <OperatorSuiteSearch
          v-model="query"
          screen-label="filtrando os insumos"
          placeholder="Buscar insumo ou SKU"
          aria-label="Buscar insumo ou SKU"
        />
      </template>
      <template #actions>
        <div v-if="minStockFilledCount" class="flex items-center gap-2 max-lg:hidden" data-min-stock-save>
          <NuxtButton label="Limpar" color="neutral" variant="outline" :disabled="actionPending" @click="clearMinStock()" />
          <NuxtButton
            icon="i-lucide-check"
            :label="saveLabel"
            :loading="saving"
            :disabled="readonlyFallback || actionPending"
            @click="onSaveMinStock()"
          />
        </div>
      </template>
      <template #filters-primary>
        <PurchaseBaseSections :counts="{ materials: materialList.total, suppliers: supplierList.total }" />
      </template>
      <template #filter-panel>
        <OperatorFilterPanel
          v-model="materialFilters"
          :dimensions="dimensions"
          surface="purchase"
          screen="materials"
          data-base-filters
        />
      </template>
      <!-- Na mesa: os filtros rápidos e a forma da tabela. No celular, os rápidos moram no
           painel (Situação) e a forma sai (as colunas de apoio já somem). -->
      <template #filters>
        <OperatorQuickFilters
          v-model="quickModel"
          :items="quickItems"
          multiple
          label="Insumos que pedem atenção"
          data-base-attention
        />
        <OperatorTableView table-key="purchase-materials" />
      </template>
      <template #filters-end>
        <span class="text-xs text-muted tabular-nums">{{ plural(materialList.total, "insumo", "insumos") }}</span>
      </template>
    </OperatorPageHeader>

    <div class="flex min-h-0 flex-1">
      <section class="min-h-0 min-w-0 flex-1 overflow-auto p-4 sm:p-6" data-base-materials>
        <PurchaseLoadState>
          <OperatorTable
            v-model:sorting="sorting"
            :data="displayed"
            :columns="columns"
            :row-key="(row: EnrichedMaterial) => row.sku"
            :row-label="(row: EnrichedMaterial) => row.name"
            :on-select="openMaterial"
            :active-key="openSku"
            view-key="purchase-materials"
            caption="Insumos da Base"
            empty-icon="i-lucide-package-search"
            :empty-title="!materials.length ? 'Nenhum insumo cadastrado na Base.' : query.trim() ? `Nenhum insumo com “${query.trim()}”.` : 'Nenhum insumo neste recorte.'"
            data-base-table
          >
            <template v-if="materialList.page > 1 || materialList.has_next" #footer>
              <NuxtPagination
                :page="materialList.page"
                :total="materialList.total"
                :items-per-page="materialList.page_size"
                aria-label="Páginas de insumos"
                @update:page="goToPage"
              />
            </template>
            <template #name-cell="{ row }">
              <span class="block min-w-24 font-semibold sm:min-w-36">{{ row.original.name }}</span>
              <span class="mt-0.5 flex flex-wrap items-center gap-1" data-base-role-tags>
                <span class="font-mono text-xs text-muted">{{ row.original.sku }}</span>
                <NuxtBadge v-if="!row.original.isActive" color="neutral" size="sm" label="Arquivado" />
                <NuxtBadge v-for="badge in skuRoleBadges(row.original.roles)" :key="badge" color="neutral" size="sm" :label="badge" class="max-sm:hidden" />
                <NuxtBadge :color="TONE_BADGE[row.original.tone]" size="sm" :label="TONE_LABEL[row.original.tone]" class="sm:hidden" />
              </span>
            </template>
            <template #stock-cell="{ row }">
              <span class="block whitespace-nowrap font-medium tabular-nums">{{ formatStockOnHand(row.original) }}</span>
              <span class="block whitespace-nowrap text-xs text-muted sm:hidden">{{ coverageLabel(row.original.coverageDays) }}</span>
            </template>
            <template #coverage-cell="{ row }">
              <span class="whitespace-nowrap tabular-nums text-muted">{{ coverageLabel(row.original.coverageDays) }}</span>
            </template>
            <!-- Sem consumo medido, o alvo de reposição é zero e o insumo nunca vira
                 sugestão. O mínimo declarado é o que destrava. O derivado do consumo NÃO
                 vai no campo: pré-preenchido, ele convidaria a "confirmar" digitando o
                 mesmo número, e isso congela um mínimo que era para acompanhar o consumo. -->
            <template #minimum-cell="{ row }">
              <div class="w-28 sm:w-32" @click.stop @keydown.stop>
                <NuxtInput
                  inputmode="decimal"
                  :model-value="minStockInputs[row.original.sku] ?? ''"
                  :placeholder="row.original.minStockDeclared ? row.original.minStock.toLocaleString('pt-BR') : 'nenhum'"
                  :aria-label="`Mínimo de ${row.original.name}`"
                  :color="minStockLineErrors[row.original.sku] ? 'error' : 'primary'"
                  :highlight="Boolean(minStockLineErrors[row.original.sku] || minStockInputs[row.original.sku])"
                  class="w-full [&_input]:text-end [&_input]:tabular-nums"
                  @update:model-value="(value: string | number) => setMinStockInput(row.original.sku, String(value ?? ''))"
                >
                  <template #trailing>
                    <span class="text-xs text-muted">{{ row.original.unit }}</span>
                  </template>
                </NuxtInput>
                <p v-if="!row.original.minStockDeclared && row.original.minStock" class="mt-0.5 text-xs text-muted">
                  pelo consumo: {{ formatQty(row.original.minStock, row.original.unit) }}
                </p>
                <p v-if="minStockLineErrors[row.original.sku]" class="mt-0.5 text-xs font-semibold text-error">
                  {{ minStockLineErrors[row.original.sku] }}
                </p>
              </div>
            </template>
            <template #cost-cell="{ row }">
              <span class="whitespace-nowrap tabular-nums" :class="row.original.preferredBaseCostQ ? '' : 'text-muted'">
                {{ row.original.preferredBaseCostQ ? `${formatMoney(row.original.preferredBaseCostQ)} / ${row.original.unit}` : "sem custo" }}
              </span>
            </template>
            <template #tone-cell="{ row }">
              <NuxtBadge :color="TONE_BADGE[row.original.tone]" :label="TONE_LABEL[row.original.tone]" />
            </template>
          </OperatorTable>
          <MoreBelow />
        </PurchaseLoadState>
      </section>

      <!-- O insumo aberto (rota filha): ao lado da tabela na mesa larga, numa folha de
           lado abaixo do `xl`. -->
      <NuxtPage />
    </div>

    <OperatorActionBar
      v-if="minStockFilledCount"
      :action="{ label: saveLabel, icon: 'i-lucide-check', loading: saving, disabled: readonlyFallback || actionPending, onSelect: () => void onSaveMinStock() }"
      :secondary="{ label: 'Limpar', onSelect: () => clearMinStock() }"
      context-label="Zero apaga o mínimo do insumo"
    />

    <PurchaseMaterialFormPanel
      :open="materialForm.open"
      :mode="materialForm.mode"
      :source="materialFormSource"
      :categories="materialCategories"
      :suppliers="suppliers"
      :conversions="materialFormConversions"
      :costs="materialFormCosts"
      :saved-version="materialSavedVersion"
      :busy="actionPending"
      :error="actionError"
      @update:open="materialForm.open = $event"
      @save="onSubmitMaterial"
      @save-conversion="onSaveMaterialConversion"
      @save-cost="onSaveMaterialCost"
    />
    <PurchaseCsvTools ref="csvTools" entity="materials" @applied="refresh()" />
  </main>
</template>
