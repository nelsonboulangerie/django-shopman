<script setup lang="ts">
// Base · Fornecedores: a tabela da suíte com os fornecedores, quantos insumos cada um
// cobre e a pontualidade. O fornecedor aberto é a rota filha (`/base/suppliers/<ref>`).
import { SUPPLIERS_TRAIL, baseSectionPath, supplierPath } from "~/presentation/purchaseSections";
import { plural, supplierDimensions } from "~/presentation/purchaseUi";
import type { Supplier } from "~/types/purchase";
import { filterBarActiveFilters } from "../../../../operator-kit/app/presentation/filterBar";

type SupplierRow = { supplier: Supplier; materialsCovered: number; preferredCount: number };

const route = useRoute();
const {
  query,
  suppliers,
  supplierList,
  materialList,
  supplierSummaries,
  supplierFilters,
  supplierForm,
  supplierFormSource,
  selectSupplier,
  openSupplierCreate,
  saveSupplier,
  saveSupplierContact,
  actionPending,
  actionError,
  refresh,
} = usePurchaseDesk();

const openRef = computed(() => (typeof route.params.ref === "string" ? route.params.ref : ""));
watch(openRef, (ref) => {
  if (ref) selectSupplier(ref);
}, { immediate: true });

const search = query;
const sorting = ref<{ id: string; desc: boolean }[]>([]);
watch(sorting, (value) => {
  const sort = value[0];
  const order = sort?.id === "name" ? (sort.desc ? "-name" : "name") : "name";
  void navigateTo({ query: { ...route.query, order, page: "1" } }, { replace: true });
}, { deep: true });
function goToPage(page: number) {
  void navigateTo({ query: { ...route.query, page: String(page) } }, { replace: true });
}

// O painel de filtros da suíte: Situação e "tem contato comercial?" — a pergunta
// que o comprador faz antes de apertar enviar.
const dimensions = computed(() => supplierDimensions(suppliers.value));
const quickItems = computed(() => [
  {
    key: "without-contact",
    label: "Sem contato comercial",
    icon: "i-lucide-user-x",
    count: suppliers.value.filter((supplier) => !supplier.orderContactName).length,
  },
]);
const quickModel = computed<string[]>({
  get: () => (supplierFilters.value.contact?.includes("without") ? ["without-contact"] : []),
  set: (keys) => {
    const next = { ...supplierFilters.value };
    delete next.contact;
    if (keys.includes("without-contact")) next.contact = ["without"];
    supplierFilters.value = next;
  },
});
const activeFilters = computed(() =>
  filterBarActiveFilters(dimensions.value, supplierFilters.value, (next) => {
    supplierFilters.value = next;
  }),
);
const SORT_VALUE: Record<string, (row: SupplierRow) => number | string> = {
  name: (row) => row.supplier.displayName,
  materials: (row) => row.materialsCovered,
  preferred: (row) => row.preferredCount,
  reliability: (row) => row.supplier.reliabilityPercent,
  lead: (row) => row.supplier.leadTimeDays,
};
// Com o fornecedor aberto ao lado, a tabela solta as colunas de apoio antes de rolar.
const yieldsToDetail = computed(() => (openRef.value ? { th: "max-2xl:hidden", td: "max-2xl:hidden" } : undefined));
const columns = computed(() => [
  { id: "name", header: "Fornecedor", accessorFn: SORT_VALUE.name, enableSorting: true, enableHiding: false },
  { id: "materials", header: "Insumos", accessorFn: SORT_VALUE.materials },
  { id: "preferred", header: "Preferidos", accessorFn: SORT_VALUE.preferred, meta: { supporting: true, class: yieldsToDetail.value } },
  { id: "reliability", header: "No prazo", accessorFn: SORT_VALUE.reliability, meta: { supporting: true } },
  { id: "lead", header: "Prazo de entrega", accessorFn: SORT_VALUE.lead, meta: { supporting: true, class: yieldsToDetail.value } },
  { id: "status", header: "Cadastro" },
]);

const displayed = computed<SupplierRow[]>(() => supplierSummaries.value);
const { remember } = useRecordTrail(SUPPLIERS_TRAIL);
watch(
  displayed,
  (list) => remember(list.map((row) => row.supplier.ref), { from: baseSectionPath("suppliers"), label: "Fornecedores" }),
  { immediate: true },
);

const headerActions = [
  { label: "Novo fornecedor", icon: "i-lucide-plus", onSelect: () => openSupplierCreate() },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];

async function onSubmitSupplier(payload: Record<string, unknown>) {
  const ref = await saveSupplier(payload);
  if (ref) await navigateTo(supplierPath(ref));
}

const supplierSavedVersion = ref(0);
async function onSaveSupplierContact(payload: Parameters<typeof saveSupplierContact>[0]) {
  if (await saveSupplierContact(payload)) supplierSavedVersion.value += 1;
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Base"
      :actions="headerActions"
      actions-label="Mais ações da Base"
      :active-filters="activeFilters"
      desk-only-filters
    >
      <template #status>
        <PurchaseReadStatus />
      </template>
      <template #search>
        <OperatorSuiteSearch
          v-model="search"
          screen-label="filtrando os fornecedores"
          placeholder="Buscar fornecedor"
          aria-label="Buscar fornecedor"
        />
      </template>
      <template #filters-primary>
        <PurchaseBaseSections :counts="{ materials: materialList.total, suppliers: supplierList.total }" />
      </template>
      <template #filter-panel>
        <OperatorFilterPanel
          v-model="supplierFilters"
          :dimensions="dimensions"
          surface="purchase"
          screen="suppliers"
          data-base-supplier-filters
        />
      </template>
      <template #filters>
        <OperatorQuickFilters
          v-model="quickModel"
          :items="quickItems"
          multiple
          label="Fornecedores sem contato comercial"
          data-base-supplier-no-contact
        />
        <OperatorTableView table-key="purchase-suppliers" />
      </template>
      <template #filters-end>
        <span class="text-xs text-muted tabular-nums">{{ plural(supplierList.total, "fornecedor", "fornecedores") }}</span>
      </template>
    </OperatorPageHeader>

    <div class="flex min-h-0 flex-1">
      <section class="min-h-0 min-w-0 flex-1 overflow-auto p-4 sm:p-6" data-base-suppliers>
        <PurchaseLoadState>
          <OperatorTable
            v-model:sorting="sorting"
            :data="displayed"
            :columns="columns"
            :row-key="(row: SupplierRow) => row.supplier.ref"
            :row-label="(row: SupplierRow) => row.supplier.displayName"
            :on-select="(row: SupplierRow) => navigateTo(supplierPath(row.supplier.ref))"
            :active-key="openRef"
            view-key="purchase-suppliers"
            caption="Fornecedores da Base"
            empty-icon="i-lucide-truck"
            :empty-title="!suppliers.length ? 'Nenhum fornecedor cadastrado ainda.' : `Nenhum fornecedor com “${search.trim()}”.`"
            data-base-suppliers-table
          >
            <template v-if="supplierList.page > 1 || supplierList.has_next" #footer>
              <NuxtPagination
                :page="supplierList.page"
                :total="supplierList.total"
                :items-per-page="supplierList.page_size"
                aria-label="Páginas de fornecedores"
                @update:page="goToPage"
              />
            </template>
            <template #name-cell="{ row }">
              <span class="block font-semibold">{{ row.original.supplier.displayName }}</span>
              <span class="block font-mono text-xs text-muted">{{ row.original.supplier.ref }}</span>
            </template>
            <template #materials-cell="{ row }">
              <span class="tabular-nums">{{ row.original.materialsCovered }}</span>
            </template>
            <template #preferred-cell="{ row }">
              <span class="tabular-nums">{{ row.original.preferredCount }}</span>
            </template>
            <template #reliability-cell="{ row }">
              <span class="tabular-nums">{{ row.original.supplier.reliabilityPercent }}%</span>
            </template>
            <template #lead-cell="{ row }">
              <span class="whitespace-nowrap tabular-nums">{{ row.original.supplier.leadTimeDays }} {{ row.original.supplier.leadTimeDays === 1 ? "dia" : "dias" }}</span>
            </template>
            <template #status-cell="{ row }">
              <NuxtBadge
                :color="row.original.supplier.isActive ? 'success' : 'neutral'"
                :label="row.original.supplier.isActive ? 'Em uso' : 'Arquivado'"
              />
            </template>
          </OperatorTable>
          <MoreBelow />
        </PurchaseLoadState>
      </section>

      <!-- O fornecedor aberto (rota filha): ao lado da tabela na mesa larga, numa folha
           de lado abaixo do `xl`. -->
      <NuxtPage />
    </div>

    <PurchaseSupplierFormPanel
      :open="supplierForm.open"
      :mode="supplierForm.mode"
      :source="supplierFormSource"
      :saved-version="supplierSavedVersion"
      :busy="actionPending"
      :error="actionError"
      @update:open="supplierForm.open = $event"
      @save="onSubmitSupplier"
      @save-contact="onSaveSupplierContact"
    />
  </main>
</template>
