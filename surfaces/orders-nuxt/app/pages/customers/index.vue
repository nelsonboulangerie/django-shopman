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
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <UiToolbar>
      <div class="flex items-center gap-2">
        <Icon name="lucide:users" class="size-4 text-muted-foreground" />
        <h1 class="text-sm font-semibold">Clientes</h1>
        <span class="hidden text-xs text-muted-foreground sm:inline">Buscar, comparar e unificar cadastros</span>
      </div>
      <template #end>
        <UiSearchInput v-model="search" placeholder="Nome, telefone, CPF…" aria-label="Buscar cliente" />
        <NuxtLink
          to="/customers/merges"
          class="inline-flex min-h-control items-center gap-1.5 rounded-md border px-3 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
        >
          <Icon name="lucide:history" class="size-4" />
          <span class="hidden sm:inline">Unificações</span>
        </NuxtLink>
        <a
          v-if="adminBaseUrl"
          :href="`${adminBaseUrl}/admin/guestman/customer/`"
          target="_blank"
          rel="noopener"
          class="inline-flex min-h-control items-center gap-1.5 rounded-md border px-3 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
          title="Cadastrar ou editar cliente (abre o Admin)"
        >
          <Icon name="lucide:settings" class="size-4" />
          <span class="hidden sm:inline">Admin</span>
          <Icon name="lucide:external-link" class="size-3.5 opacity-60" />
        </a>
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </UiToolbar>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <div class="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Filtrar clientes">
        <UiFilterChip
          v-for="option in list?.filters ?? []"
          :key="option.ref"
          :active="option.active"
          :aria-pressed="option.active"
          :data-customer-filter="option.ref"
          @click="setFilter(option.ref)"
        >
          {{ option.label }}
        </UiFilterChip>
        <span v-if="list" class="ml-auto text-xs text-muted-foreground tabular-nums" data-customer-total>{{ list.total_label }}</span>
      </div>

      <div v-if="error" role="alert" class="mb-3 rounded-md border border-destructive p-3 text-sm">
        {{ httpErrorMessage(error, "Não foi possível carregar os clientes.") }}
        {{ list ? "Exibindo a última lista carregada." : "" }}
        <button type="button" class="ml-2 min-h-11 underline" @click="refresh()">Tentar de novo</button>
      </div>

      <div v-if="loading" class="space-y-2">
        <div v-for="i in 6" :key="i" class="h-14 animate-pulse rounded-lg border bg-muted/40"></div>
      </div>

      <ul v-else-if="items.length" class="divide-y rounded-lg border bg-card" data-customer-list>
        <li v-for="row in items" :key="row.ref">
          <NuxtLink
            :to="`/customers/${encodeURIComponent(row.ref)}`"
            class="grid gap-1 px-4 py-3 transition hover:bg-accent sm:grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,1fr)] sm:items-center sm:gap-4"
            :data-customer-row="row.ref"
          >
            <span class="min-w-0">
              <span class="flex flex-wrap items-center gap-2">
                <span class="truncate font-medium">{{ row.name }}</span>
                <span v-if="row.source_label" class="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{{ row.source_label }}</span>
                <span
                  v-if="row.duplicate_hint"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-500/15 dark:text-amber-200"
                >{{ row.duplicate_hint }}</span>
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

      <p v-else-if="list" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        {{ list.total_label }}.
      </p>

      <nav v-if="list && (list.page > 1 || list.has_next)" class="mt-3 flex items-center justify-between" aria-label="Páginas">
        <button
          type="button"
          class="min-h-control rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-40"
          :disabled="list.page <= 1 || pending"
          @click="goToPage(list.page - 1)"
        >
          Anteriores
        </button>
        <span class="text-xs text-muted-foreground tabular-nums">Página {{ list.page }}</span>
        <button
          type="button"
          class="min-h-control rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-40"
          :disabled="!list.has_next || pending"
          @click="goToPage(list.page + 1)"
        >
          Próximos
        </button>
      </nav>
    </section>
  </main>
</template>
