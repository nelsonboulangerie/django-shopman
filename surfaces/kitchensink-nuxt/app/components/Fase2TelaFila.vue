<script setup lang="ts">
// Tela composta 1: a Fila do Gestor com TUDO ligado ao mesmo tempo (rodada 2). No
// celular: selo ao vivo + busca + Avisos + ⋯, filtros com 2 recortes ativos, 3 pedidos
// marcados, a ação flutuante, a barra inferior e o aviso urgente. Na mesa: a mesma tela
// em colunas, com a barra de seleção no lugar da toolbar.
import { computed, ref } from "vue";

import { ORDER_DIMENSIONS, ORDER_QUICK, ORDER_TEXT_FIELDS, ORDER_VIEWS, PERIODS, QUEUE } from "../data/fase2";
import type { Fase2FilterConfig } from "../data/fase2Filters";
import { applyView, edit, facetsOf, removeFacet } from "../data/fase2Filters";
import type { Fase2FilterState, QuickFilter, SavedView } from "../types/fase2";

const props = defineProps<{ estado: string }>();

const sections = [
  { key: "queue", label: "Pedidos", icon: "i-lucide-list-checks", badge: "5" },
  { key: "out", label: "Saída", icon: "i-lucide-package-check" },
  { key: "history", label: "Histórico", icon: "i-lucide-history" },
  { key: "customers", label: "Clientes", icon: "i-lucide-users" },
  { key: "catalog", label: "Catálogo", icon: "i-lucide-book-open" },
];

const config: Fase2FilterConfig = {
  noun: "pedidos",
  quick: ORDER_QUICK,
  periods: PERIODS.filter((period) => ["today", "tomorrow"].includes(period.value)),
  defaultPeriod: "today",
  groups: [],
  dimensions: ORDER_DIMENSIONS,
  textFields: ORDER_TEXT_FIELDS,
};

const views = ref<SavedView[]>(ORDER_VIEWS.map((view) => ({ ...view })));
const filters = ref<Fase2FilterState>(
  props.estado === "favorito"
    ? applyView(ORDER_VIEWS[0]!, "today")
    : edit({ quick: [], period: "today", groupBy: "", values: {}, text: [], favorite: "" }, {
        values: { channel: ["ifood"], payment: ["pix"] },
      }),
);
// O favorito fixado que está ativo como aba JÁ é o recorte à vista: não repete em chip.
const facets = computed(() =>
  facetsOf(filters.value, config, views.value).filter((facet) => !(facet.favorite && scope.value === filters.value.favorite)),
);

const scope = ref(props.estado === "favorito" ? "ifood-late" : "needs");
function pickScope(value: string) {
  scope.value = value;
  const view = views.value.find((item) => item.id === value);
  if (view) filters.value = applyView(view, "today");
}
const scopes = computed<QuickFilter[]>(() => [
  { value: "needs", label: "Precisa de você", count: 5 },
  { value: "all", label: "Todos", count: 18 },
  { value: "ready", label: "Prontos", count: 3 },
  ...views.value.filter((view) => view.pinned).map((view) => ({ value: view.id, label: view.name, favorite: true })),
]);

const empty = computed(() => props.estado === "vazio");
const failed = computed(() => props.estado === "erro");
const orders = computed(() => (empty.value || failed.value ? [] : QUEUE));
const columns = computed(() => [
  { key: "new", label: "Novos", items: orders.value.filter((o) => o.stage === "Novo" || o.stage === "Atrasado") },
  { key: "prep", label: "Em preparo", items: orders.value.filter((o) => o.stage === "Em preparo") },
  { key: "ready", label: "Prontos", items: orders.value.filter((o) => o.stage === "Pronto") },
]);

const selection = ref<Record<string, boolean>>(
  ["selecao", "favorito"].includes(props.estado) || !props.estado ? { "1051": true, "1053": true, "1055": true } : {},
);
const selected = computed(() => Object.keys(selection.value).filter((key) => selection.value[key]));
function clearSelection() {
  selection.value = {};
}

const searchItems = QUEUE.slice(0, 3).map((order) => ({
  label: `${order.ref} · ${order.customer}`,
  suffix: order.stage,
  icon: "i-lucide-receipt",
}));
function filterByText(term: string) {
  filters.value = edit(filters.value, { text: [...filters.value.text, { field: "customer", term }] });
}

const actions = [
  [{ label: "Novo pedido", icon: "i-lucide-plus", class: "sm:hidden" }],
  [
    { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"] },
    { label: "Imprimir a fila", icon: "i-lucide-printer" },
  ],
];
</script>

<template>
  <Fase2Screen storage-key="fase2-fila" :sections="sections" label="Seções do Gestor de pedidos" current="queue">
    <template #header>
      <Fase2Header
        title="Pedidos"
        :live="{ label: 'Ao vivo · 10:42', color: 'success' }"
        :primary="{ label: 'Novo pedido', icon: 'i-lucide-plus' }"
        :actions="actions"
        :inbox="2"
      >
        <template #search>
          <Fase2Search
            screen="a fila"
            :screen-items="searchItems"
            app="Gestor"
            :app-items="[
              { label: '0998 · Ana Souza', suffix: 'Histórico · retirado ontem', icon: 'i-lucide-history' },
              { label: 'Ana Souza', suffix: 'Clientes · 12 pedidos', icon: 'i-lucide-user' },
            ]"
            :suite-items="[
              { label: 'Croissant', suffix: 'Catálogo', icon: 'i-lucide-croissant' },
              { label: 'Fim do dia', suffix: 'PDV', icon: 'i-lucide-app-window' },
            ]"
            :open-on-mount="estado === 'busca'"
            @filter="filterByText"
          />
        </template>
      </Fase2Header>
    </template>

    <template #toolbar>
      <!-- Mesa com marcados: a barra de seleção OCUPA o lugar da toolbar (dono, Q3=1),
           e diz em que recorte a seleção foi feita. No celular a toolbar fica: a seleção
           é a ação flutuante. -->
      <div v-if="selected.length" class="flex min-h-12 items-center gap-2 px-3 py-1.5 max-lg:hidden" data-fase2-bulk-bar>
        <span class="text-sm font-semibold" aria-live="polite">{{ selected.length }} selecionados</span>
        <NuxtButton label="Limpar seleção" color="neutral" variant="ghost" @click="clearSelection" />
        <span class="min-w-0 text-sm text-pretty text-muted">em {{ [scopes.find((s) => s.value === scope)?.label, ...facets.map((f) => f.label)].join(" · ") }}</span>
        <div class="ms-auto flex items-center gap-2">
          <NuxtButton :label="`Avançar ${selected.length}`" icon="i-lucide-arrow-right" color="neutral" variant="outline" />
          <NuxtButton :label="`Aceitar ${selected.length}`" icon="i-lucide-check" />
        </div>
      </div>
      <div
        class="flex min-h-12 items-center gap-2 px-2 py-1.5 sm:px-3"
        :class="selected.length ? 'lg:hidden' : ''"
        data-fase2-toolbar
      >
        <Fase2QuickFilters :model-value="scope" :items="scopes" label="Recorte da fila" class="min-w-0 flex-1 sm:flex-none" @update:model-value="pickScope" />
        <Fase2Facets :facets="facets" class="max-sm:hidden" @remove="(id) => (filters = removeFacet(filters, id, 'today'))" />
        <span class="ms-auto text-sm tabular-nums text-muted max-sm:hidden">{{ orders.length }} pedidos</span>
        <Fase2Filters
          v-model="filters"
          v-model:views="views"
          :config="config"
          :result-count="orders.length"
          :open-on-mount="estado === 'filtros'"
        />
      </div>
      <div v-if="facets.length" class="border-t border-default px-2 py-1.5 sm:hidden">
        <Fase2Facets :facets="facets" scroll @remove="(id) => (filters = removeFacet(filters, id, 'today'))" />
      </div>
    </template>

    <div class="space-y-3 p-2 sm:p-3">
      <NuxtAlert
        v-if="!empty && !failed"
        color="error"
        variant="subtle"
        icon="i-lucide-alarm-clock"
        title="O 1049 está 12 min atrasado"
        description="iFood. O entregador chega às 10:50."
        :actions="[
          { label: 'Abrir o 1049', color: 'error', variant: 'outline' },
          { label: 'Mais 1 aviso', color: 'neutral', variant: 'ghost' },
        ]"
        data-fase2-role="alert"
      />

      <Fase2ScreenState v-if="empty" kind="empty" noun="a fila" />
      <Fase2ScreenState v-else-if="failed" kind="error" noun="a fila" />
      <div v-else class="grid gap-3 lg:grid-cols-3">
        <section v-for="column in columns" :key="column.key" :aria-label="column.label" class="space-y-2">
          <h2 class="flex items-baseline gap-2 px-1 text-sm font-semibold text-highlighted">
            {{ column.label }} <span class="font-normal tabular-nums text-muted">{{ column.items.length }}</span>
          </h2>
          <Fase2OrderCard
            v-for="order in column.items"
            :key="order.ref"
            :order="order"
            :selected="Boolean(selection[order.ref])"
            @update:selected="(value) => (selection = { ...selection, [order.ref]: value })"
          />
        </section>
      </div>
    </div>

    <template v-if="!empty && !failed" #base>
      <Fase2ActionBar
        v-if="selected.length"
        context-label="Selecionados"
        :context-value="`${selected.length} pedidos`"
        :action="`Aceitar ${selected.length}`"
        icon="i-lucide-check"
        secondary="Limpar"
        @secondary="clearSelection"
      />
      <Fase2ActionBar
        v-else
        context-label="Próximo: 1051 · Bruno Lima"
        context-value="R$ 62,40"
        action="Aceitar o 1051"
        icon="i-lucide-check"
      />
    </template>
  </Fase2Screen>
</template>
