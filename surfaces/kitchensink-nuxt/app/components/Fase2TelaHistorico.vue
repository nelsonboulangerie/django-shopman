<script setup lang="ts">
// Tela composta 2: o Histórico do Gestor na mesa, com tudo ao mesmo tempo (rodada 2):
// tabela compacta, uma linha aberta, 3 marcados (a barra de seleção no lugar da
// toolbar), um favorito aplicado e o detalhe ao lado com anterior/próximo.
import { useLocalStorage } from "@vueuse/core";
import { computed, onMounted, ref } from "vue";

import { HISTORY, ORDER_DIMENSIONS, ORDER_QUICK, ORDER_TEXT_FIELDS, ORDER_VIEWS, PERIODS, ORDER_GROUPS, brl } from "../data/fase2";
import type { Fase2FilterConfig } from "../data/fase2Filters";
import { applyView, edit, facetsOf, removeFacet } from "../data/fase2Filters";
import type { Fase2FilterState, QuickFilter, SavedView } from "../types/fase2";

const props = defineProps<{ estado: string }>();
const all = !props.estado || props.estado === "tudo";

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
  periods: PERIODS,
  defaultPeriod: "",
  groups: ORDER_GROUPS,
  dimensions: ORDER_DIMENSIONS,
  textFields: ORDER_TEXT_FIELDS,
};
const views = ref<SavedView[]>(ORDER_VIEWS.map((view) => ({ ...view })));
const filters = ref<Fase2FilterState>(
  props.estado === "livre"
    ? { quick: [], period: "7d", groupBy: "", values: {}, text: [], favorite: "" }
    : applyView(ORDER_VIEWS[0]!, ""),
);
// O favorito fixado que está ativo como aba JÁ é o recorte à vista: não repete em chip.
const facets = computed(() =>
  facetsOf(filters.value, config, views.value).filter((facet) => !(facet.favorite && scope.value === filters.value.favorite)),
);
function remove(id: string) {
  filters.value = removeFacet(filters.value, id, "");
  scope.value = "all";
}

const scope = ref(props.estado === "livre" ? "all" : "ifood-late");
const scopes = computed<QuickFilter[]>(() => [
  { value: "all", label: "Todos", count: 214 },
  { value: "done", label: "Concluídos", count: 198 },
  { value: "canceled", label: "Cancelados", count: 16 },
  ...views.value.filter((view) => view.pinned).map((view) => ({ value: view.id, label: view.name, favorite: true })),
]);
function pickScope(value: string) {
  scope.value = value;
  const view = views.value.find((item) => item.id === value);
  filters.value = view ? applyView(view, "") : edit(filters.value, {});
}

const tableFilter = ref("");
const density = useLocalStorage<"compact" | "comfortable">("fase2-table-density", "compact", { initOnMounted: true });
const visibility = ref<Record<string, boolean>>({});
const viewColumns = [
  { id: "date", label: "Dia" },
  { id: "customer", label: "Cliente" },
  { id: "channel", label: "Canal" },
  { id: "payment", label: "Pagamento" },
  { id: "stage", label: "Situação" },
  { id: "total_q", label: "Total" },
];

const rows = HISTORY;
const selection = ref<Record<string, boolean>>(
  all || props.estado === "selecao" ? { "1044": true, "1041": true, "1038": true } : {},
);
const selected = computed(() => rows.filter((row) => selection.value[row.ref]));
const selectedTotal = computed(() => brl(selected.value.reduce((sum, row) => sum + row.total_q, 0)));
function clearSelection() {
  selection.value = {};
}
const expanded = ref<Record<string, boolean>>(props.estado === "livre" ? {} : { "1044": true });

// O detalhe: na mesa, uma coluna que DIVIDE a tela com a tabela (a tabela solta Canal e
// Pagamento enquanto ele está aberto); abaixo de `lg`, a tela inteira. A escolha de
// contêiner no toque é comportamento (lida depois de montar), não estrutura do servidor.
const detailOpen = ref(all || props.estado === "detalhe");
const phoneDetail = ref(false);
const detailIndex = ref(rows.findIndex((row) => row.ref === "1041"));
const detail = computed(() => rows[detailIndex.value] ?? rows[0]!);
const narrow = () => window.matchMedia("(max-width: 1023.98px)").matches;
onMounted(() => {
  if (props.estado === "detalhe" && narrow()) phoneDetail.value = true;
});
function open(ref: string) {
  detailIndex.value = rows.findIndex((row) => row.ref === ref);
  if (narrow()) phoneDetail.value = true;
  else detailOpen.value = true;
}
const context = computed(() => (facets.value.length ? facets.value.map((facet) => facet.label).join(" · ") : "Todos"));
const shownColumns = computed(() =>
  detailOpen.value ? { ...visibility.value, channel: false, payment: false } : visibility.value,
);

const actions = [
  [
    { label: "Exportar a lista", icon: "i-lucide-download" },
    { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"] },
  ],
];
</script>

<template>
  <Fase2Screen storage-key="fase2-historico" :sections="sections" label="Seções do Gestor de pedidos" current="history">
    <template #header>
      <Fase2Header title="Histórico" :actions="actions" :inbox="2">
        <template #search>
          <Fase2Search
            screen="o histórico"
            :screen-items="rows.slice(0, 3).map((row) => ({ label: `${row.ref} · ${row.customer}`, suffix: row.stage, icon: 'i-lucide-receipt' }))"
            app="Gestor"
            :app-items="[{ label: 'Ana Souza', suffix: 'Clientes · 12 pedidos', icon: 'i-lucide-user' }]"
            :suite-items="[{ label: 'Croissant', suffix: 'Catálogo', icon: 'i-lucide-croissant' }]"
            @filter="(term) => (filters = edit(filters, { text: [...filters.text, { field: 'customer', term }] }))"
          />
        </template>
      </Fase2Header>
    </template>

    <template #toolbar>
      <div v-if="selected.length" class="flex min-h-12 flex-wrap items-center gap-2 px-3 py-1.5 max-lg:hidden" data-fase2-bulk-bar>
        <span class="text-sm font-semibold" aria-live="polite">{{ selected.length }} selecionados</span>
        <NuxtButton label="Limpar seleção" color="neutral" variant="ghost" @click="clearSelection" />
        <span class="text-sm text-muted">
          em {{ facets.length ? facets.map((f) => f.label).join(" · ") : "Todos" }} · {{ selectedTotal }}
        </span>
        <div class="ms-auto flex items-center gap-2">
          <NuxtButton label="Imprimir as vias" icon="i-lucide-printer" color="neutral" variant="outline" />
          <NuxtButton :label="`Exportar ${selected.length}`" icon="i-lucide-download" />
        </div>
      </div>
      <div
        class="flex min-h-12 flex-wrap items-center gap-2 px-2 py-1.5 sm:px-3"
        :class="selected.length ? 'lg:hidden' : ''"
        data-fase2-toolbar
      >
        <NuxtInput
          v-model="tableFilter"
          icon="i-lucide-search"
          placeholder="Filtrar estes pedidos"
          aria-label="Filtrar os pedidos da tabela"
          class="w-52 shrink-0 max-sm:hidden"
          data-fase2-table-search
        />
        <Fase2QuickFilters :model-value="scope" :items="scopes" label="Recorte do histórico" class="min-w-0 flex-1 sm:flex-none" @update:model-value="pickScope" />
        <Fase2Facets :facets="facets" class="max-xl:hidden" @remove="remove" />
        <div class="ms-auto flex shrink-0 items-center gap-2">
          <Fase2Filters v-model="filters" v-model:views="views" :config="config" :result-count="37" :open-on-mount="estado === 'filtros'" />
          <Fase2TableView v-model:density="density" v-model:visibility="visibility" :columns="viewColumns" />
        </div>
      </div>
      <div v-if="facets.length" class="border-t border-default px-2 py-1.5 xl:hidden" :class="selected.length ? 'lg:hidden' : ''">
        <Fase2Facets :facets="facets" scroll @remove="remove" />
      </div>
    </template>

    <div class="flex items-start gap-3 p-2 sm:p-3">
      <NuxtCard class="min-w-0 flex-1" :ui="{ body: 'p-0 sm:p-0' }">
        <Fase2Table
          v-model:global-filter="tableFilter"
          v-model:row-selection="selection"
          v-model:expanded="expanded"
          :column-visibility="shownColumns"
          :rows="rows"
          :density="density"
          :active-ref="detailOpen ? detail.ref : ''"
          caption="Pedidos do histórico (exemplo)"
          @update:column-visibility="(value) => (visibility = value)"
          @open="open"
        />
        <p class="border-t border-default px-3 py-2 text-sm tabular-nums text-muted" data-fase2-table-count>37 pedidos</p>
      </NuxtCard>
      <!-- Mesa: o detalhe divide a tela, fixo no topo da área que rola. -->
      <NuxtCard
        v-if="detailOpen"
        class="sticky top-3 w-96 shrink-0 max-lg:hidden"
        :ui="{ body: 'p-0 sm:p-0' }"
        aria-label="Pedido aberto"
      >
        <Fase2OrderDetail
          :order="detail"
          :index="detailIndex"
          :total="rows.length"
          :context="context"
          @go="detailIndex = $event"
          @close="detailOpen = false"
        />
      </NuxtCard>
    </div>

    <template v-if="selected.length" #base>
      <Fase2ActionBar
        context-label="Selecionados"
        :context-value="`${selected.length} pedidos · ${selectedTotal}`"
        :action="`Exportar ${selected.length}`"
        icon="i-lucide-download"
        secondary="Limpar"
        @secondary="clearSelection"
      />
    </template>
  </Fase2Screen>

  <!-- Abaixo de lg: o pedido é a tela inteira, com o mesmo anterior/próximo. -->
  <NuxtSlideover v-model:open="phoneDetail" side="right" :title="`Pedido ${detail.ref}`" :description="detail.customer" :ui="{ content: 'max-w-none' }">
    <template #content>
      <Fase2OrderDetail
        :order="detail"
        :index="detailIndex"
        :total="rows.length"
        :context="context"
        @go="detailIndex = $event"
        @close="phoneDetail = false"
      />
    </template>
  </NuxtSlideover>
</template>
