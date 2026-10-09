<script setup lang="ts">
// Clientes — achar o cadastro, inclusive o que ninguém digitou.
//
// O caso que abriu a seção: o cadastro do iFood (`IF-…`) nasce sem telefone e, até
// 19/09/2026, nascia um por pedido. A busca e os filtros daqui são o caminho para
// achá-lo; a ficha (`/customers/<ref>`) é onde se compara e unifica. A URL guarda a
// busca, então voltar da ficha devolve a mesma lista.
import {
  listQueryFromRoute,
  routeQueryFromList,
  type CustomerFilter,
} from "~/presentation/customers";

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

// Criar e editar cadastro continua no Admin; esta seção acha, compara e unifica.
const adminBaseUrl = useRuntimeConfig().public.adminBaseUrl as string;

const items = computed(() => list.value?.items ?? []);
type CustomerRow = (typeof items.value)[number];
const filterItems = computed(() =>
  (list.value?.filters ?? []).map((option) => ({
    value: option.ref,
    label: option.label,
  })),
);
// Cliente é a chave (fixada); Pedidos é de apoio (some no celular).
const customerColumns = [
  { id: "customer", header: "Cliente", enableHiding: false },
  { id: "contact", header: "Contato" },
  { id: "orders", header: "Pedidos", meta: { supporting: true } },
];
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const phoneHeaderActions = computed(() => [
  { label: "Unificações", icon: "i-lucide-history", to: "/customers/merges" },
  ...(adminBaseUrl
    ? [{ label: "Cadastrar ou editar no Admin", icon: "i-lucide-settings", to: `${adminBaseUrl}/admin/guestman/customer/`, target: "_blank" }]
    : []),
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
        <NuxtTabs
          :model-value="listQuery.filter"
          :items="filterItems"
          :content="false"
          variant="pill"
          aria-label="Filtrar clientes"
          @update:model-value="setFilter(String($event))"
        />
      </template>
      <template #filters>
        <div class="flex items-center gap-3">
          <NuxtButton
            to="/customers/merges"
            icon="i-lucide-history"
            label="Unificações"
            color="neutral"
            variant="outline"
          />
          <NuxtButton
            v-if="adminBaseUrl"
            :to="`${adminBaseUrl}/admin/guestman/customer/`"
            target="_blank"
            icon="i-lucide-settings"
            trailing-icon="i-lucide-external-link"
            label="Admin"
            color="neutral"
            variant="outline"
            title="Cadastrar ou editar cliente (abre o Admin)"
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
        :data="items"
        :columns="customerColumns"
        :row-key="(row: CustomerRow) => row.ref"
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
  </main>
</template>
