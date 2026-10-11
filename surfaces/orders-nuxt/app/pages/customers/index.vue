<script setup lang="ts">
// Clientes — achar o cadastro, inclusive o que ninguém digitou.
//
// O caso que abriu a seção: o cadastro do iFood (`IF-…`) nasce sem telefone e, até
// 19/09/2026, nascia um por pedido. A busca e os filtros daqui são o caminho para
// achá-lo; a ficha (`/customers/<ref>`) é onde se compara e unifica. A URL guarda a
// busca, então voltar da ficha devolve a mesma lista.
import { listQueryFromRoute, routeQueryFromList, type CustomerFilter } from "~/presentation/customers";

useHead({ title: "Clientes" });

const route = useRoute();
const router = useRouter();
const listQuery = computed(() => listQueryFromRoute(route.query));
const { list, pending, error, refresh, readMetadata } = useCustomerList(listQuery);

const search = ref(listQuery.value.q);
watch(() => listQuery.value.q, (q) => { if (q !== search.value.trim()) search.value = q; });
watchDebounced(search, (q) => {
  if (q.trim() === listQuery.value.q) return;
  router.replace({ query: routeQueryFromList({ ...listQuery.value, q: q.trim(), page: 1 }) });
}, { debounce: 300 });

function setFilter(filter: string) {
  router.replace({ query: routeQueryFromList({ ...listQuery.value, filter: filter as CustomerFilter, page: 1 }) });
}
function goToPage(page: number) {
  router.replace({ query: routeQueryFromList({ ...listQuery.value, page }) });
}

// Criar e editar cadastro continua no Admin; esta seção acha, compara e unifica.
const adminBaseUrl = useRuntimeConfig().public.adminBaseUrl as string;

const items = computed(() => list.value?.items ?? []);
const loading = computed(() => pending.value && !list.value);
const filterItems = computed(() => (list.value?.filters ?? []).map((option) => ({ value: option.ref, label: option.label })));
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Clientes">
      <template #status>
        <span class="hidden op-micro text-muted-foreground lg:inline">Buscar, comparar e unificar cadastros</span>
      </template>
      <template #search>
        <OperatorSuiteSearch v-model="search" screen-label="filtrando os clientes" placeholder="Nome, telefone, CPF…" aria-label="Buscar cliente" />
      </template>
      <template #actions>
        <NuxtButton to="/customers/merges" icon="i-lucide-history" label="Unificações" color="neutral" variant="outline" />
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
        <NuxtButton icon="i-lucide-refresh-cw" label="Atualizar" :loading="pending" @click="refresh()" />
      </template>
    </OperatorPageHeader>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <NuxtTabs
          :model-value="listQuery.filter"
          :items="filterItems"
          :content="false"
          variant="pill"
          aria-label="Filtrar clientes"
          @update:model-value="setFilter(String($event))"
        />
        <span v-if="list" class="ml-auto text-xs text-muted-foreground tabular-nums" data-customer-total>{{ list.total_label }}</span>
      </div>

      <NuxtAlert v-if="error" color="error" variant="subtle" icon="i-lucide-triangle-alert" title="Não foi possível carregar os clientes" :description="`${httpErrorMessage(error, 'Não foi possível carregar os clientes.')} ${list ? 'Exibindo a última lista carregada.' : ''}`" :actions="[{ label: 'Tentar de novo', color: 'error', variant: 'outline', onClick: () => refresh() }]" />

      <div v-if="loading" class="space-y-2">
        <NuxtSkeleton
          v-for="i in 6"
          :key="i"
         
          label="Carregando clientes"
        />
      </div>

      <NuxtCard v-else-if="items.length" data-customer-list>
      <ul class="divide-y">
        <li v-for="row in items" :key="row.ref">
          <NuxtLink
            :to="`/customers/${encodeURIComponent(row.ref)}`"
            class="grid gap-1 px-4 py-3 transition hover:bg-accent sm:grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,1fr)] sm:items-center sm:gap-4"
            :data-customer-row="row.ref"
          >
            <span class="min-w-0">
              <span class="flex flex-wrap items-center gap-2">
                <span class="truncate font-medium">{{ row.name }}</span>
                <NuxtBadge v-if="row.source_label" color="neutral" variant="subtle" :label="row.source_label" />
                <NuxtBadge
                  v-if="row.duplicate_hint"
                  color="warning"
                  variant="subtle"
                  :label="row.duplicate_hint"
                />
              </span>
              <span class="font-mono text-xs text-muted-foreground">{{ row.ref }}</span>
            </span>
            <span class="text-sm">
              <span :class="row.phone_display ? '' : 'text-muted-foreground'">{{ row.phone_display || "Sem telefone" }}</span>
              <span v-if="row.document_display" class="block text-xs text-muted-foreground">CPF {{ row.document_display }}</span>
            </span>
            <span class="text-sm text-muted-foreground">
              {{ row.orders_label }}<template v-if="row.last_order_display"> · último {{ row.last_order_display }}</template>
            </span>
          </NuxtLink>
        </li>
      </ul>
      </NuxtCard>

      <NuxtEmpty v-else-if="list" icon="i-lucide-users" title="Nenhum cliente neste recorte" :description="`${list.total_label}.`" />

      <nav v-if="list && (list.page > 1 || list.has_next)" class="mt-3 flex items-center justify-between" aria-label="Páginas">
        <NuxtButton
          type="button"
         
          :disabled="list.page <= 1 || pending"
          @click="goToPage(list.page - 1)"
        >
          Anteriores
        </NuxtButton>
        <span class="text-xs text-muted-foreground tabular-nums">Página {{ list.page }}</span>
        <NuxtButton
          type="button"
         
          :disabled="!list.has_next || pending"
          @click="goToPage(list.page + 1)"
        >
          Próximos
        </NuxtButton>
      </nav>
    </section>
  </main>
</template>
