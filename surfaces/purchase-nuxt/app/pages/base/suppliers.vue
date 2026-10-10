<script setup lang="ts">
// Base · Fornecedores: a tabela da suíte com os fornecedores, quantos insumos cada um
// cobre e a pontualidade. O fornecedor aberto é a rota filha (`/base/suppliers/<ref>`).
import { SUPPLIERS_TRAIL, baseSectionPath, supplierPath } from "~/presentation/purchaseSections";
import { plural } from "~/presentation/purchaseUi";
import type { Supplier } from "~/types/purchase";

type SupplierRow = { supplier: Supplier; materialsCovered: number; preferredCount: number };

const route = useRoute();
const { suppliers, supplierSummaries, metrics, selectSupplier, refresh } = usePurchaseDesk();

const openRef = computed(() => (typeof route.params.ref === "string" ? route.params.ref : ""));
watch(openRef, (ref) => {
  if (ref) selectSupplier(ref);
}, { immediate: true });

const search = ref("");
const sorting = ref<{ id: string; desc: boolean }[]>([]);
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
  { id: "materials", header: "Insumos", accessorFn: SORT_VALUE.materials, enableSorting: true },
  { id: "preferred", header: "Preferidos", accessorFn: SORT_VALUE.preferred, enableSorting: true, meta: { supporting: true, class: yieldsToDetail.value } },
  { id: "reliability", header: "No prazo", accessorFn: SORT_VALUE.reliability, enableSorting: true, meta: { supporting: true } },
  { id: "lead", header: "Prazo de entrega", accessorFn: SORT_VALUE.lead, enableSorting: true, meta: { supporting: true, class: yieldsToDetail.value } },
  { id: "status", header: "Situação" },
]);

const displayed = computed<SupplierRow[]>(() => {
  const term = search.value.trim().toLowerCase();
  const list = supplierSummaries.value.filter(
    (row) =>
      !term ||
      row.supplier.displayName.toLowerCase().includes(term) ||
      row.supplier.name.toLowerCase().includes(term) ||
      row.supplier.ref.toLowerCase().includes(term),
  );
  const sort = sorting.value[0];
  const value = sort ? SORT_VALUE[sort.id] : undefined;
  if (!sort || !value) return list;
  return [...list].sort((a, b) => {
    const left = value(a);
    const right = value(b);
    const order = typeof left === "string" ? left.localeCompare(String(right), "pt-BR") : left - (right as number);
    return sort.desc ? -order : order;
  });
});
const { remember } = useRecordTrail(SUPPLIERS_TRAIL);
watch(
  displayed,
  (list) => remember(list.map((row) => row.supplier.ref), { from: baseSectionPath("suppliers"), label: "Fornecedores" }),
  { immediate: true },
);

const headerActions = [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Base" :actions="headerActions" actions-label="Mais ações da Base">
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
        <PurchaseBaseSections current="suppliers" :counts="{ materials: metrics.activeMaterials, suppliers: suppliers.length }" />
      </template>
      <template #filters>
        <OperatorTableView table-key="purchase-suppliers" />
      </template>
      <template #filters-end>
        <span class="text-xs text-muted tabular-nums">{{ plural(displayed.length, "fornecedor", "fornecedores") }}</span>
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
              <NuxtBadge :color="row.original.supplier.isActive ? 'success' : 'neutral'" :label="row.original.supplier.isActive ? 'Ativo' : 'Inativo'" />
            </template>
          </OperatorTable>
          <MoreBelow />
        </PurchaseLoadState>
      </section>

      <!-- O fornecedor aberto (rota filha): ao lado da tabela na mesa larga, numa folha
           de lado abaixo do `xl`. -->
      <NuxtPage />
    </div>
  </main>
</template>
