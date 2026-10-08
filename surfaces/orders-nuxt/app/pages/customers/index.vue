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
const loading = computed(() => pending.value && !list.value);
const filterItems = computed(() =>
  (list.value?.filters ?? []).map((option) => ({
    value: option.ref,
    label: option.label,
  })),
);
const customerColumns = [
  { id: "customer", header: "Cliente" },
  { id: "contact", header: "Contato" },
  { id: "orders", header: "Pedidos" },
];
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Clientes" :filters-wrap="false">
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
      <template #filters>
        <NuxtTabs
          :model-value="listQuery.filter"
          :items="filterItems"
          :content="false"
          variant="pill"
          aria-label="Filtrar clientes"
          @update:model-value="setFilter(String($event))"
        />
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
          <NuxtButton
            icon="i-lucide-refresh-cw"
            label="Atualizar"
            color="neutral"
            variant="outline"
            :loading="pending"
            @click="refresh()"
          />
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

    <section class="min-h-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível carregar os clientes"
        :description="`${httpErrorMessage(error, 'Não foi possível carregar os clientes.')} ${list ? 'Exibindo a última lista carregada.' : ''}`"
        :actions="[
          {
            label: 'Tentar de novo',
            color: 'error',
            variant: 'outline',
            onClick: () => refresh(),
          },
        ]"
      />

      <div v-if="loading" class="space-y-2">
        <NuxtSkeleton
          v-for="i in 6"
          :key="i"
          class="h-12 w-full"
          aria-label="Carregando clientes"
        />
      </div>

      <!-- Tabela integrada a um card branco, sem padding (o tema tira o padding do
           corpo quando a tabela é o conteúdo inteiro), como a Lista do Gestor. -->
      <NuxtCard v-else-if="items.length" class="min-w-0">
        <NuxtTable
          :data="items"
          :columns="customerColumns"
          :get-row-id="(row) => row.ref"
          :on-select="
            (_event, row) =>
              router.push(`/customers/${encodeURIComponent(row.original.ref)}`)
          "
          caption="Clientes encontrados"
          data-customer-list
        >
          <template #customer-cell="{ row }">
            <div class="min-w-52" :data-customer-row="row.original.ref">
              <span class="flex flex-wrap items-center gap-2">
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
        </NuxtTable>
        <template v-if="list && (list.page > 1 || list.has_next)" #footer>
          <div class="flex items-center justify-between gap-3">
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
      </NuxtCard>

      <NuxtEmpty
        v-else-if="list"
        icon="i-lucide-users"
        title="Nenhum cliente neste recorte"
        :description="`${list.total_label}.`"
      />
    </section>
  </main>
</template>
