<script setup lang="ts">
// A linha do chão no celular (abaixo de `md`), do modelo de navegação (31/10/2026): o
// cabeçalho inteiro numa linha, no fundo claro da barra do kit (`bg-card`).
//   [selo: app + lugar ▾, chip de conexão] [Busca] [⋮ Opções] [Avisos]
// - O selo diz o app e o lugar e abre o trocador (`OperatorSwitcher`). O nome do lugar
//   também fica no <h1> acessível. Tela de REGISTRO (detalhe, conferência) usa `#lead`
//   para o voltar e `#identity` para o que identifica o registro, que nunca some.
// - A cadência e a hora da última leitura moram no topo das Opções.
// - Filtros: `#filters` vira o painel de baixo, aberto por "Filtros" dentro do ⋮.
// - Busca: ícone; abre a busca da suíte (mesmo contrato do app). O termo ativo aparece na
//   faixa logo abaixo, com contagem e Limpar, sempre visível (o cabeçalho não rola).
import { computed, getCurrentInstance, ref, useSlots } from "vue";

import type { OperatorMoreMenuItem, OperatorMoreMenuItems } from "../presentation/moreMenu";

type Tone = "live" | "calm" | "late" | "off";

const props = withDefaults(defineProps<{
  title: string;
  tone?: Tone;
  time?: string;
  connLabel?: string;
  query?: string;
  /** O nome do botão de busca (o que a busca acha). Vira `aria-label`. */
  searchButtonLabel?: string;
  search?: boolean;
  filterActive?: boolean;
  filterLabel?: string;
  summary?: string;
  /** As ações da tela no ⋮ (o formato do `OperatorMoreMenu`: lista ou grupos). */
  options?: OperatorMoreMenuItems;
}>(), {
  query: "",
  searchButtonLabel: "Buscar",
  search: true,
  filterActive: false,
  filterLabel: "",
  summary: "",
  options: () => [],
  connLabel: "",
});
const emit = defineEmits<{ clear: []; search: [] }>();
const inst = getCurrentInstance();
const ownSearch = Boolean(inst?.vnode.props?.onSearch);
const slots = useSlots();
const filtersOpen = ref(false);
const { request: openSuiteSearch } = useSuiteSearchRequest();
function onSearch() {
  if (ownSearch) emit("search");
  else openSuiteSearch();
}
const active = computed(() => Boolean(props.query.trim() || props.filterActive));
const CONN_ICON = { live: "i-lucide-check", calm: "i-lucide-refresh-cw", late: "i-lucide-clock", off: "i-lucide-x" } as const;
const connLine = computed(() => {
  if (!props.tone) return "";
  const at = props.time ? ` Lida às ${props.time}.` : "";
  if (props.tone === "off") return `Sem conexão.${at}`;
  if (props.tone === "late") return `Leitura atrasada.${at}`;
  if (props.tone === "live") return `Ao vivo.${at}`;
  return `${props.connLabel || "Atualização periódica"}.${at}`;
});
// A leitura (cadência e hora) abre o ⋮ como rótulo do primeiro grupo: rótulo sozinho não
// vira grupo no `OperatorMoreMenu`, então ele encabeça Filtros ou as ações da tela.
const items = computed<(readonly OperatorMoreMenuItem[])[]>(() => {
  const conn: OperatorMoreMenuItem[] = props.tone
    ? [{ label: connLine.value, icon: CONN_ICON[props.tone], type: "label" }]
    : [];
  const filters: OperatorMoreMenuItem[] = slots.filters
    ? [{
        label: props.filterActive ? `Filtros: ${props.filterLabel}` : "Filtros",
        icon: "i-lucide-list-filter",
        onSelect: () => (filtersOpen.value = true),
      }]
    : [];
  const options = props.options;
  const rest: (readonly OperatorMoreMenuItem[])[] = !options.length
    ? []
    : options.every((entry) => Array.isArray(entry))
      ? [...(options as readonly (readonly OperatorMoreMenuItem[])[])]
      : [options as readonly OperatorMoreMenuItem[]];
  if (filters.length) return [[...conn, ...filters], ...rest];
  if (rest.length) return [[...conn, ...rest[0]!], ...rest.slice(1)];
  return [];
});
</script>

<template>
  <div class="md:hidden" data-compact-header>
    <h1 class="sr-only">{{ title }}</h1>
    <div class="flex min-h-14 items-center gap-1.5 border-b border-default bg-card px-2 py-1.5" data-compact-bar>
      <slot name="lead"><OperatorCompactSeal :tone="tone" :time="time" :place="title" /></slot>
      <div v-if="$slots.identity" class="min-w-0 flex-1" data-compact-identity><slot name="identity" /></div>
      <div class="flex shrink-0 items-center" role="group" :aria-label="`Buscar e opções: ${title}`">
        <NuxtButton
          v-if="search"
          icon="i-lucide-search"
          square
          :color="query ? 'primary' : 'neutral'"
          variant="ghost"
          class="size-11 justify-center"
          :aria-label="query ? `Buscar. Busca ativa: ${query}` : searchButtonLabel"
          data-compact-search
          @click="onSearch"
        />
        <OperatorMoreMenu
          v-if="items.length"
          :items="items"
          :label="`Mais ações: ${title}`"
          class="size-11 justify-center"
          data-compact-options
        />
      </div>
      <!-- O sino do kit desenha alvo de 32px; na linha compacta ele ganha os 44px da casa. -->
      <div class="shrink-0 [&_button]:size-11 [&_button]:justify-center" data-compact-inbox>
        <ClientOnly><OperatorInbox placement="header" /></ClientOnly>
      </div>
    </div>
    <div v-if="active" class="flex items-center gap-2 border-b border-default bg-elevated/50 px-3 py-1 text-sm" role="status" data-compact-active>
      <NuxtIcon :name="query ? 'i-lucide-search' : 'i-lucide-list-filter'" class="size-4 shrink-0 text-primary" />
      <p class="min-w-0 flex-1 break-words">
        <span v-if="query">Busca <strong>{{ query }}</strong>. </span><span v-if="filterActive && filterLabel">{{ filterLabel }}. </span>{{ summary }}
      </p>
      <NuxtButton color="neutral" variant="ghost" class="min-h-11 shrink-0" label="Limpar" aria-label="Limpar busca e filtros" @click="emit('clear')" />
    </div>
    <NuxtDrawer v-if="$slots.filters" v-model:open="filtersOpen" :title="`Filtros: ${title}`" description="Recortes desta tela.">
      <template #title>
        <div class="flex w-full items-center gap-2">
          <span class="flex-1">Filtros</span>
          <NuxtButton icon="i-lucide-x" square aria-label="Fechar filtros" variant="ghost" color="neutral" class="size-11 justify-center" @click="filtersOpen = false" />
        </div>
      </template>
      <template #body><div class="flex flex-col gap-3"><slot name="filters" :close="() => (filtersOpen = false)" /></div></template>
      <template #footer>
        <div class="flex gap-2">
          <NuxtButton label="Limpar" color="neutral" variant="ghost" class="min-h-11" :disabled="!filterActive" @click="emit('clear')" />
          <NuxtButton label="Ver resultados" class="min-h-11 flex-1 justify-center" @click="filtersOpen = false" />
        </div>
      </template>
    </NuxtDrawer>
  </div>
</template>
