<script setup lang="ts">
// Tela composta 3: a Base do Compras no celular (rodada 2). Hoje o topo dela ocupa 362 px
// (43% da tela, laudo G3). Aqui: a barra primária, UMA toolbar com as sub-seções e o
// ícone de filtros, os chips do recorte, o aviso e a lista longa, agrupada por
// fornecedor com o cabeçalho do grupo grudado sob a toolbar.
import { computed, ref } from "vue";

import { MATERIALS, MATERIAL_DIMENSIONS, MATERIAL_GROUPS, MATERIAL_QUICK, MATERIAL_VIEWS } from "../data/fase2";
import type { Fase2FilterConfig } from "../data/fase2Filters";
import { edit, facetsOf, removeFacet } from "../data/fase2Filters";
import type { Fase2FilterState, Fase2Material, QuickFilter, SavedView } from "../types/fase2";

const props = defineProps<{ estado: string }>();

const sections = [
  { key: "panel", label: "Painel", icon: "i-lucide-layout-dashboard", badge: "3" },
  { key: "buy", label: "Comprar", icon: "i-lucide-shopping-cart" },
  { key: "receive", label: "Receber", icon: "i-lucide-package-open" },
  { key: "base", label: "Base", icon: "i-lucide-database" },
  { key: "settings", label: "Ajustes", icon: "i-lucide-settings", foot: true },
];

const config: Fase2FilterConfig = {
  noun: "insumos",
  quick: MATERIAL_QUICK,
  periods: [],
  defaultPeriod: "",
  groups: MATERIAL_GROUPS,
  dimensions: MATERIAL_DIMENSIONS,
  textFields: [
    { value: "name", label: "Nome" },
    { value: "sku", label: "Código" },
  ],
};
const views = ref<SavedView[]>(MATERIAL_VIEWS.map((view) => ({ ...view })));
const filters = ref<Fase2FilterState>({
  quick: [],
  period: "",
  groupBy: props.estado === "livre" ? "" : "supplier",
  values: {},
  text: [],
  favorite: "",
});
const facets = computed(() => facetsOf(filters.value, config, views.value));

// A sub-seção é navegação (muda a URL); na toolbar ela fica com a faixa esquerda.
const subsection = ref("materials");
const subsections: QuickFilter[] = [
  { value: "materials", label: "Insumos", count: 108, to: "/base/materials" },
  { value: "suppliers", label: "Fornecedores", count: 23, to: "/base/suppliers" },
  { value: "costs", label: "Custos", to: "/base/costs" },
  { value: "count", label: "Contagem", to: "/base/count" },
];

const items = computed(() =>
  filters.value.quick.includes("low") ? MATERIALS.filter((item) => item.low) : MATERIALS,
);
const groups = computed(() => {
  const key = filters.value.groupBy as keyof Fase2Material | "";
  if (!key) return [{ label: "", items: items.value }];
  const names = [...new Set(items.value.map((item) => String(item[key])))].sort();
  return names.map((name) => ({ label: name, items: items.value.filter((item) => item[key] === name) }));
});
const lowCount = MATERIALS.filter((item) => item.low).length;

const actions = [
  [{ label: "Novo insumo", icon: "i-lucide-plus", class: "sm:hidden" }],
  [
    { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"] },
    { label: "Exportar a lista", icon: "i-lucide-download" },
  ],
];
</script>

<template>
  <Fase2Screen storage-key="fase2-compras" :sections="sections" label="Seções do Compras" current="base">
    <template #header>
      <Fase2Header title="Base" :primary="{ label: 'Novo insumo', icon: 'i-lucide-plus' }" :actions="actions" :inbox="1">
        <template #search>
          <Fase2Search
            screen="os insumos"
            :screen-items="MATERIALS.slice(0, 3).map((item) => ({ label: item.name, suffix: item.sku, icon: 'i-lucide-wheat' }))"
            app="Compras"
            :app-items="[{ label: 'Moinho Paraná', suffix: 'Fornecedores', icon: 'i-lucide-truck' }]"
            :suite-items="[{ label: 'Croissant', suffix: 'Produção · ficha', icon: 'i-lucide-croissant' }]"
            :open-on-mount="estado === 'busca'"
            @filter="(term) => (filters = edit(filters, { text: [...filters.text, { field: 'name', term }] }))"
          />
        </template>
      </Fase2Header>
    </template>

    <template #toolbar>
      <div class="flex min-h-12 items-center gap-2 px-2 py-1.5 sm:px-3" data-fase2-toolbar>
        <Fase2QuickFilters v-model="subsection" :items="subsections" label="Seção da Base" :select-above="3" class="min-w-0 flex-1 sm:flex-none" />
        <Fase2Facets :facets="facets" class="max-lg:hidden" @remove="(id) => (filters = removeFacet(filters, id, ''))" />
        <span class="ms-auto text-sm tabular-nums text-muted max-sm:hidden">{{ items.length }} insumos</span>
        <Fase2Filters
          v-model="filters"
          v-model:views="views"
          :config="config"
          :result-count="items.length"
          :open-on-mount="estado === 'filtros'"
        />
      </div>
      <div v-if="facets.length" class="border-t border-default px-2 py-1.5 lg:hidden">
        <Fase2Facets :facets="facets" scroll @remove="(id) => (filters = removeFacet(filters, id, ''))" />
      </div>
    </template>

    <div class="space-y-3 p-2 sm:p-3">
      <NuxtAlert
        v-if="!filters.quick.includes('low')"
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        :title="`${lowCount} insumos abaixo do mínimo`"
        :actions="[{ label: `Ver os ${lowCount}`, color: 'warning', variant: 'outline', onClick: () => (filters = edit(filters, { quick: ['low'] })) }]"
        data-fase2-role="alert"
      />

      <NuxtCard :ui="{ body: 'p-0 sm:p-0' }">
        <section v-for="group in groups" :key="group.label" :aria-label="group.label || 'Insumos'">
          <h2
            v-if="group.label"
            class="sticky top-0 z-1 flex items-baseline gap-2 border-b border-default bg-elevated px-3 py-1.5 text-sm font-semibold text-highlighted"
          >
            {{ group.label }} <span class="font-normal tabular-nums text-muted">{{ group.items.length }}</span>
          </h2>
          <ul class="divide-y divide-default">
            <li v-for="item in group.items" :key="item.sku" class="flex items-start gap-3 px-3 py-2" :data-fase2-material="item.sku">
              <div class="min-w-0 flex-1">
                <p class="text-sm text-highlighted">{{ item.name }}</p>
                <p class="text-xs text-muted">{{ item.sku }} · {{ item.category }}</p>
              </div>
              <div class="shrink-0 text-end">
                <p class="text-sm tabular-nums" :class="item.low ? 'font-semibold text-warning' : 'text-default'">{{ item.stock }}</p>
                <p class="text-xs tabular-nums text-muted">mín. {{ item.min }}</p>
              </div>
            </li>
          </ul>
        </section>
      </NuxtCard>
      <MoreBelow />
    </div>
  </Fase2Screen>
</template>
