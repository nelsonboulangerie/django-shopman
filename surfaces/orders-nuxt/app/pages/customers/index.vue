<script setup lang="ts">
// Clientes — achar o cadastro, inclusive o que ninguém digitou.
//
// O caso que abriu a seção: o cadastro do iFood (`IF-…`) nasce sem telefone e, até
// 19/09/2026, nascia um por pedido. A busca e os filtros daqui são o caminho para
// achá-lo; a ficha (`/customers/<ref>`) é onde se compara e unifica. A URL guarda a
// busca, então voltar da ficha devolve a mesma lista.
import type { ActiveFilters, FilterDimension } from "../../../../operator-kit/app/types/filters";
import { filterBarActiveFilters } from "../../../../operator-kit/app/presentation/filterBar";
import {
  customersCsv,
  listQueryFromRoute,
  routeQueryFromList,
  type CustomerFilter,
  type CustomerSort,
} from "~/presentation/customers";
import type { OperatorBulkItem } from "../../../../operator-kit/app/presentation/bulkBar";
import type { CustomerFormOptionsProjection } from "~/generated/ordersContract";
import type { CustomerBulkOperation, CustomerMutationPayload } from "~/types/customers";
import type { CustomerGroupMembersOperation } from "~/types/customerGroups";
import {
  customerGroupsLabel,
  groupMembersResultMessage,
} from "~/presentation/customerGroupMembers";
import { mutationFieldErrors } from "~/utils/mutationFieldErrors";

useHead({ title: "Clientes" });

const route = useRoute();
const router = useRouter();
const listQuery = computed(() => listQueryFromRoute(route.query));
const { list, pending, error, refresh, readMetadata } =
  useCustomerList(listQuery);

const search = ref(listQuery.value.q);
watch(
  () => listQuery.value.q,
  (q) => {
    if (q !== search.value.trim()) search.value = q;
  },
);
watchDebounced(
  search,
  (q) => {
    if (q.trim() === listQuery.value.q) return;
    router.replace({
      query: routeQueryFromList({ ...listQuery.value, q: q.trim(), page: 1 }),
    });
  },
  { debounce: 300 },
);

function setFilter(filter: string) {
  router.replace({
    query: routeQueryFromList({
      ...listQuery.value,
      filter: filter as CustomerFilter,
      page: 1,
    }),
  });
}
function goToPage(page: number) {
  router.replace({ query: routeQueryFromList({ ...listQuery.value, page }) });
}
function setSort(sort: string) {
  router.replace({
    query: routeQueryFromList({ ...listQuery.value, sort: sort as CustomerSort, page: 1 }),
  });
}

const createOpen = ref(false);
const createBusy = ref(false);
const createError = ref("");
const createFieldErrors = ref<Record<string, string>>({});
watch(createOpen, (open) => {
  if (!open) return;
  createError.value = "";
  createFieldErrors.value = {};
});
let createKey = crypto.randomUUID();
const emptyForm: CustomerFormOptionsProjection = { customer_types: [], price_tiers: [] };
const formOptions = computed(() => list.value?.form ?? emptyForm);

async function saveCustomer(payload: CustomerMutationPayload) {
  if (createBusy.value) return;
  createBusy.value = true;
  createError.value = "";
  createFieldErrors.value = {};
  try {
    const response = await createCustomer(payload, createKey);
    if (response.outcome !== "applied" || !response.customer) {
      createError.value = "O resultado ainda não foi confirmado. Tente salvar novamente; a mesma intenção será reutilizada.";
      return;
    }
    createKey = crypto.randomUUID();
    createOpen.value = false;
    useSonner.success(`${response.customer.name} foi cadastrado.`);
    await refresh();
    await router.push(`/customers/${encodeURIComponent(response.customer.ref)}`);
  } catch (failure) {
    createError.value = httpErrorMessage(failure, "Não foi possível cadastrar o cliente.");
    createFieldErrors.value = mutationFieldErrors(failure);
    if (httpError(failure).status) createKey = crypto.randomUUID();
  } finally {
    createBusy.value = false;
  }
}

const items = computed(() => list.value?.items ?? []);
type CustomerRow = (typeof items.value)[number];
// O painel de filtros único (fase 2, K4): os recortes da lista como um campo de
// escolha única, e os favoritos da pessoa. As abas continuam como os filtros rápidos à
// vista; o painel e as abas mexem no mesmo `?filter=`.
// O grupo comercial é a segunda dimensão: é por ele que se acha quem tirar de um grupo.
const groupOptions = computed(() => formOptions.value.price_tiers);
const panelDimensions = computed<FilterDimension[]>(() => [
  {
    id: "filter",
    label: "Recorte",
    type: "single-select",
    options: (list.value?.filters ?? [])
      .filter((option) => option.ref !== "all")
      .map((option) => ({ value: option.ref, label: option.label })),
  },
  {
    id: "group",
    label: "Grupo",
    type: "single-select",
    options: groupOptions.value.map((option) => ({ value: option.value, label: option.label })),
  },
]);
const panelFilters = computed<ActiveFilters>({
  get: (): ActiveFilters => ({
    ...(listQuery.value.filter === "all" ? {} : { filter: [String(listQuery.value.filter)] }),
    ...(listQuery.value.group ? { group: [listQuery.value.group] } : {}),
  }),
  set: (next: ActiveFilters) => {
    router.replace({
      query: routeQueryFromList({
        ...listQuery.value,
        filter: (next.filter?.[0] ?? "all") as CustomerFilter,
        group: next.group?.[0] ?? "",
        page: 1,
      }),
    });
  },
});
const activeFilters = computed(() =>
  filterBarActiveFilters(panelDimensions.value, panelFilters.value, (next) => {
    panelFilters.value = next;
  }),
);
const filterItems = computed(() =>
  (list.value?.filters ?? []).map((option) => ({
    key: option.ref,
    label: option.label,
  })),
);
// Cliente é a chave (fixada); Grupos e Pedidos são de apoio (somem no celular).
const customerColumns = [
  { id: "customer", header: "Cliente", enableHiding: false },
  { id: "contact", header: "Contato" },
  { id: "groups", header: "Grupos", meta: { supporting: true } },
  { id: "orders", header: "Pedidos", meta: { supporting: true } },
];

// Seleção da lista e a barra de lote: etiquetar a seleção numa ida e exportar o que
// está marcado. A seleção atravessa páginas; trocar busca ou recorte a limpa, porque
// aí a pergunta mudou. O servidor ignora cadastro inativo ou que sumiu.
const selected = ref<Set<string>>(new Set());
const customerRowSelection = computed<Record<string, boolean>>({
  get: () => Object.fromEntries([...selected.value].map((ref_) => [ref_, true])),
  set: (next) => {
    selected.value = new Set(Object.keys(next).filter((key) => next[key]));
  },
});
function clearSelection() {
  selected.value = new Set();
}
watch(
  () => [listQuery.value.q, listQuery.value.filter, listQuery.value.group] as const,
  clearSelection,
);

const bulkScope = computed(() => {
  const current = (list.value?.filters ?? []).find(
    (option) => option.ref === listQuery.value.filter,
  );
  const group = groupOptions.value.find((option) => option.value === listQuery.value.group);
  return [current && current.ref !== "all" ? current.label : "", group ? `grupo ${group.label}` : ""]
    .filter(Boolean)
    .join(" · ");
});

const bulkOpen = ref(false);
const bulkBusy = ref(false);
const bulkError = ref("");
let bulkKey = crypto.randomUUID();
watch(bulkOpen, (open) => {
  if (!open) return;
  bulkError.value = "";
});
function bulkItems(_placement: "toolbar" | "base"): OperatorBulkItem[] {
  return [
    {
      label: "Mudar grupo…",
      shortLabel: "Grupo…",
      icon: "i-lucide-badge-percent",
      disabled: bulkBusy.value || groupBusy.value,
      onSelect: () => {
        groupOpen.value = true;
      },
    },
    {
      label: "Etiquetar…",
      icon: "i-lucide-tags",
      disabled: bulkBusy.value || groupBusy.value,
      onSelect: () => {
        bulkOpen.value = true;
      },
    },
    {
      label: "Exportar CSV",
      shortLabel: "CSV",
      icon: "i-lucide-download",
      disabled: bulkBusy.value,
      onSelect: () => exportSelectionCsv(),
    },
  ];
}
async function saveBulkTags({
  operation,
  tags,
}: {
  operation: CustomerBulkOperation;
  tags: string[];
}) {
  if (bulkBusy.value || selected.value.size === 0) return;
  bulkBusy.value = true;
  bulkError.value = "";
  try {
    const response = await bulkCustomers(
      { refs: [...selected.value], operation, tags },
      bulkKey,
    );
    if (response.outcome !== "applied") {
      bulkError.value = "O resultado ainda não foi confirmado. Tente de novo; a mesma intenção será reutilizada.";
      return;
    }
    bulkKey = crypto.randomUUID();
    bulkOpen.value = false;
    const verb = response.operation === "add_tags" ? "Etiqueta aplicada em " : "Etiqueta removida de ";
    const many = response.applied.length === 1 ? " cadastro" : " cadastros";
    const skipped = response.skipped.length
      ? " " + response.skipped.length + " ficaram de fora."
      : "";
    useSonner.success(verb + response.applied.length + many + "." + skipped);
    clearSelection();
    await refresh();
  } catch (failure) {
    bulkError.value = httpErrorMessage(failure, "Não foi possível aplicar as etiquetas.");
    if (httpError(failure).status) bulkKey = crypto.randomUUID();
  } finally {
    bulkBusy.value = false;
  }
}
// Mudar grupo em lote: pôr a seleção num grupo, ou tirar dele, numa ida. A chave
// de intenção vale para o par grupo + gesto; trocar qualquer um gera outra.
const groupOpen = ref(false);
const groupBusy = ref(false);
const groupError = ref("");
let groupKey = crypto.randomUUID();
let groupKeyScope = "";
watch(groupOpen, (open) => {
  if (open) groupError.value = "";
});
async function saveGroupMembers({
  operation,
  groupRef,
}: {
  operation: CustomerGroupMembersOperation;
  groupRef: string;
}) {
  if (groupBusy.value || selected.value.size === 0) return;
  const scope = operation + ":" + groupRef + ":" + [...selected.value].sort().join(",");
  if (scope !== groupKeyScope) {
    groupKey = crypto.randomUUID();
    groupKeyScope = scope;
  }
  groupBusy.value = true;
  groupError.value = "";
  try {
    const response = await changeCustomerGroupMembers(
      groupRef,
      { operation, refs: [...selected.value] },
      groupKey,
    );
    if (response.outcome !== "applied") {
      groupError.value = "O resultado ainda não foi confirmado. Tente de novo; a mesma intenção será reutilizada.";
      return;
    }
    groupKey = crypto.randomUUID();
    groupKeyScope = "";
    groupOpen.value = false;
    useSonner.success(groupMembersResultMessage(response));
    clearSelection();
    await refresh();
  } catch (failure) {
    groupError.value = httpErrorMessage(failure, "Não foi possível mudar o grupo.");
    if (httpError(failure).status) {
      groupKey = crypto.randomUUID();
      groupKeyScope = "";
    }
  } finally {
    groupBusy.value = false;
  }
}
function exportSelectionCsv() {
  const chosen = items.value.filter((row) => selected.value.has(row.ref));
  if (!chosen.length) return;
  const csv = customersCsv(chosen);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "clientes-" + new Date().toISOString().slice(0, 10) + ".csv";
  anchor.click();
  URL.revokeObjectURL(url);
}
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const phoneHeaderActions = computed(() => [
  { label: "Cadastrar cliente", icon: "i-lucide-user-round-plus", onSelect: () => { createOpen.value = true; } },
  { label: "Grupos", icon: "i-lucide-badge-percent", to: "/customers/groups" },
  { label: "Unificações", icon: "i-lucide-history", to: "/customers/merges" },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Clientes"
      :filters-wrap="false"
      :phone-actions="phoneHeaderActions"
      desk-only-filters
      :active-filters="activeFilters"
    >
      <template #status>
        <span class="hidden op-micro text-muted-foreground lg:inline"
          >Buscar, comparar e unificar cadastros</span
        >
      </template>
      <template #search>
        <OperatorSuiteSearch
          v-model="search"
          screen-label="filtrando os clientes"
          placeholder="Nome, telefone, CPF…"
          aria-label="Buscar cliente"
        />
      </template>
      <template #filters-primary>
        <OperatorQuickFilters
          :model-value="listQuery.filter"
          :items="filterItems"
          label="Filtrar clientes"
          @update:model-value="setFilter(String($event))"
        />
      </template>
      <template #filter-panel>
        <OperatorFilterPanel
          v-model="panelFilters"
          :dimensions="panelDimensions"
          surface="orders"
          screen="customers"
          :chips="false"
        />
      </template>
      <template v-if="selected.size" #selection>
        <OperatorBulkBar
          :count="selected.size"
          :scope="bulkScope"
          :items="bulkItems('toolbar')"
          data-customers-bulk
          @clear="clearSelection"
        />
      </template>
      <template #filters>
        <div class="flex items-center gap-3">
          <NuxtButton
            icon="i-lucide-user-round-plus"
            label="Cadastrar cliente"
            @click="createOpen = true"
          />
          <NuxtButton
            to="/customers/groups"
            icon="i-lucide-badge-percent"
            label="Grupos"
            color="neutral"
            variant="outline"
          />
          <NuxtButton
            to="/customers/merges"
            icon="i-lucide-history"
            label="Unificações"
            color="neutral"
            variant="outline"
          />
          <NuxtSelect
            :model-value="listQuery.sort"
            :items="[{ value: 'recent', label: 'Mais recentes' }, { value: 'name', label: 'Nome' }]"
            value-key="value"
            label-key="label"
            aria-label="Ordenar clientes"
            @update:model-value="setSort(String($event))"
          />
          <OperatorTableView table-key="orders-customers" />
          <NuxtButton
            icon="i-lucide-refresh-cw"
            label="Atualizar"
            color="neutral"
            variant="outline"
            :loading="pending"
            @click="refresh()"
          />
        </div>
      </template>
      <template #filters-end>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span
            v-if="list"
            class="text-xs text-muted-foreground tabular-nums"
            data-customer-total
            >{{ list.total_label }}</span
          >
          <ReadFreshness
            inline
            :metadata="readMetadata"
            :failed="Boolean(error)"
          />
        </div>
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <OperatorTable
        v-model:row-selection="customerRowSelection"
        :data="items"
        :columns="customerColumns"
        :row-key="(row: CustomerRow) => row.ref"
        selectable
        :row-label="(row: CustomerRow) => `o cadastro de ${row.name}`"
        :on-select="
          (row: CustomerRow) =>
            router.push(`/customers/${encodeURIComponent(row.ref)}`)
        "
        :loading="pending"
        :error="Boolean(error)"
        what="os clientes"
        :error-description="list ? 'Exibindo a última lista carregada.' : ''"
        empty-icon="i-lucide-users"
        empty-title="Nenhum cliente neste recorte."
        :empty-description="list ? `${list.total_label}.` : ''"
        pinned="customer"
        view-key="orders-customers"
        caption="Clientes encontrados"
        data-customer-list
        @retry="refresh()"
      >
        <template #customer-cell="{ row }">
          <div :data-customer-row="row.original.ref">
            <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <NuxtLink
                :to="`/customers/${encodeURIComponent(row.original.ref)}`"
                class="font-medium hover:underline"
                >{{ row.original.name }}</NuxtLink
              >
              <NuxtBadge
                v-if="row.original.source_label"
                color="neutral"
                :label="row.original.source_label"
              />
              <NuxtBadge
                v-if="row.original.duplicate_hint"
                color="warning"
                :label="row.original.duplicate_hint"
              />
            </span>
            <span class="block font-mono text-xs text-muted-foreground">{{
              row.original.ref
            }}</span>
          </div>
        </template>
        <template #contact-cell="{ row }">
          <span
            :class="row.original.phone_display ? '' : 'text-muted-foreground'"
            >{{ row.original.phone_display || "Sem telefone" }}</span
          >
          <span
            v-if="row.original.document_display"
            class="block text-xs text-muted-foreground"
            >CPF {{ row.original.document_display }}</span
          >
        </template>
        <template #groups-cell="{ row }">
          <span
            :class="row.original.groups.length ? '' : 'text-muted-foreground'"
            :data-customer-groups="row.original.ref"
            >{{ customerGroupsLabel(row.original.groups) || "Sem grupo" }}</span
          >
        </template>
        <template #orders-cell="{ row }">
          <span class="text-muted-foreground">
            {{ row.original.orders_label
            }}<template v-if="row.original.last_order_display">
              · último {{ row.original.last_order_display }}</template
            >
          </span>
        </template>
        <template v-if="list && (list.page > 1 || list.has_next)" #footer>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <span class="op-micro text-muted-foreground tnum">{{
              list.total_label
            }}</span>
            <NuxtPagination
              :page="list.page"
              :total="list.total"
              :items-per-page="list.page_size"
              :disabled="pending"
              aria-label="Páginas"
              @update:page="goToPage"
            />
          </div>
        </template>
      </OperatorTable>
    </section>

    <OperatorBulkBar
      v-if="selected.size"
      placement="base"
      :count="selected.size"
      :scope="bulkScope"
      :items="bulkItems('base')"
      data-customers-bulk
      @clear="clearSelection"
    />

    <CustomerGroupBulkDialog
      v-model:open="groupOpen"
      :count="selected.size"
      :groups="groupOptions"
      :initial-group="listQuery.group"
      :busy="groupBusy"
      :error="groupError"
      @save="saveGroupMembers"
    />

    <CustomerBulkTagsPanel
      v-model:open="bulkOpen"
      :count="selected.size"
      :busy="bulkBusy"
      :error="bulkError"
      @save="saveBulkTags"
    />

    <CustomerFormPanel
      v-model:open="createOpen"
      :options="formOptions"
      :busy="createBusy"
      :error="createError"
      :field-errors="createFieldErrors"
      @save="saveCustomer"
    />
  </main>
</template>
