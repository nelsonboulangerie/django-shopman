<script setup lang="ts">
// PRÉVIA do modo compacto no celular (abaixo de `md`): o cabeçalho inteiro numa linha.
//   [selo do app + chip de conexão] [Filtro | Busca elástica | ⋮ Opções] [Avisos]
// - O título da SEÇÃO não se repete: a seção é a vaga ativa da barra inferior/lateral, e o
//   nome fica no <h1> acessível. Tela de REGISTRO (detalhe, conferência) usa `#lead` para
//   o voltar e `#identity` para o que identifica o registro, que nunca some.
// - A cadência e a hora da última leitura moram no topo das Opções.
// - Filtro: `#filters` vira o painel de baixo; sem o slot, não há botão de filtro.
// - Busca: um botão com o termo ativo; abre a busca da suíte (mesmo contrato do app).
// - Busca/recorte ativos: faixa logo abaixo, com contagem e Limpar, sempre visível (o
//   cabeçalho não rola).
const props = withDefaults(defineProps<{
  title: string; tone?: 'live' | 'calm' | 'late' | 'off'; time?: string; connLabel?: string;
  query?: string; searchLabel?: string; search?: boolean;
  filterActive?: boolean; filterLabel?: string; summary?: string;
  options?: Array<any>; avisos?: 'own' | 'options' | 'none'; to?: string;
}>(), { query: '', searchLabel: 'Buscar', search: true, filterActive: false, filterLabel: '', summary: '', options: () => [], avisos: 'own', connLabel: '' });
const emit = defineEmits<{ clear: []; search: [] }>();
const inst = getCurrentInstance();
const ownSearch = Boolean(inst?.vnode.props?.onSearch);
const filtersOpen = ref(false);
const { request: openSuiteSearch } = useSuiteSearchRequest();
function onSearch() { if (ownSearch) emit('search'); else openSuiteSearch(); }
const active = computed(() => Boolean(props.query.trim() || props.filterActive));
const inboxHost = ref<HTMLElement | null>(null);
// O menu fecha e devolve o foco ao ⋮; abrir a caixa no mesmo tique a fecharia de novo.
function openInbox() { setTimeout(() => inboxHost.value?.querySelector('button')?.click(), 180); }
const CONN_ICON = { live: 'i-lucide-check', calm: 'i-lucide-refresh-cw', late: 'i-lucide-clock', off: 'i-lucide-x' } as const;
const connLine = computed(() => {
  if (!props.tone) return '';
  const at = props.time ? ` Lida às ${props.time}.` : '';
  if (props.tone === 'off') return `Sem conexão.${at}`;
  if (props.tone === 'late') return `Leitura atrasada.${at}`;
  if (props.tone === 'live') return `Ao vivo.${at}`;
  return `${props.connLabel || 'Atualização periódica'}.${at}`;
});
const items = computed(() => [
  ...(props.tone ? [[{ label: connLine.value, icon: CONN_ICON[props.tone], type: 'label' as const }]] : []),
  ...(props.avisos === 'options' ? [[{ label: 'Avisos', icon: 'i-lucide-bell', onSelect: openInbox }]] : []),
  ...(Array.isArray(props.options[0]) ? props.options : props.options.length ? [props.options] : []),
]);
</script>
<template>
  <div class="md:hidden" data-compact-header>
    <h1 class="sr-only">{{ title }}</h1>
    <div class="flex min-h-14 items-center gap-1.5 border-b border-default px-2 py-1.5" data-compact-bar>
      <slot name="lead"><OperatorCompactSeal :tone="tone" :time="time" :to="to" /></slot>
      <div v-if="$slots.identity" class="min-w-0 flex-1" data-compact-identity><slot name="identity" /></div>
      <div v-if="search || $slots.filters || items.length" class="flex min-w-0 items-stretch overflow-hidden rounded-lg border border-default bg-default"
        :class="$slots.identity ? 'shrink-0' : 'flex-1'" role="group" :aria-label="'Filtrar, buscar e opções: ' + title">
        <NuxtButton v-if="$slots.filters" icon="i-lucide-list-filter" square color="neutral" variant="ghost"
          class="size-11 shrink-0 justify-center rounded-none border-r border-default" :class="filterActive ? 'text-primary' : ''"
          :aria-label="filterActive ? 'Filtros: ' + filterLabel : 'Filtros'" aria-haspopup="dialog" :aria-expanded="filtersOpen" @click="filtersOpen = true" />
        <NuxtButton v-if="search" icon="i-lucide-search" color="neutral" variant="ghost" class="min-h-11 min-w-0 flex-1 justify-start rounded-none px-2.5"
          :class="$slots.identity ? 'w-11 flex-none justify-center px-0' : ''"
          :aria-label="query ? 'Buscar. Busca ativa: ' + query : searchLabel" @click="onSearch">
          <span v-if="!$slots.identity" class="min-w-0 truncate text-left" :class="query ? 'font-semibold text-highlighted' : 'text-muted'">{{ query || 'Buscar' }}</span>
        </NuxtButton>
        <div v-if="items.length" class="relative shrink-0">
          <NuxtDropdownMenu :items="items" :content="{ align: 'end' }" :ui="{ content: 'w-72 max-w-[calc(100vw-24px)]', label: 'whitespace-normal font-normal text-muted', itemLabel: 'whitespace-normal' }">
            <NuxtButton icon="i-lucide-ellipsis-vertical" square color="neutral" variant="ghost" class="size-11 justify-center rounded-none" :class="search || $slots.filters ? 'border-l border-default' : ''" :aria-label="'Opções: ' + title" data-compact-options />
          </NuxtDropdownMenu>
          <div v-if="avisos === 'options'" ref="inboxHost" class="pointer-events-none absolute inset-0 opacity-0" aria-hidden="true" inert><ClientOnly><OperatorInbox placement="header" /></ClientOnly></div>
        </div>
      </div>
      <!-- O sino do kit desenha alvo de 32px; na linha compacta ele ganha os 44px da casa. -->
      <div v-if="avisos === 'own'" class="shrink-0 [&_button]:size-11 [&_button]:justify-center" data-compact-inbox><ClientOnly><OperatorInbox placement="header" /></ClientOnly></div>
    </div>
    <div v-if="active" class="flex items-center gap-2 border-b border-default bg-elevated/50 px-3 py-1 text-sm" role="status" data-compact-active>
      <NuxtIcon :name="query ? 'i-lucide-search' : 'i-lucide-list-filter'" class="size-4 shrink-0 text-primary" />
      <p class="min-w-0 flex-1 break-words"><span v-if="query">Busca <strong>{{ query }}</strong>. </span><span v-if="filterActive && filterLabel">{{ filterLabel }}. </span>{{ summary }}</p>
      <NuxtButton color="neutral" variant="ghost" class="min-h-11 shrink-0" label="Limpar" aria-label="Limpar busca e filtros" @click="emit('clear')" />
    </div>
    <NuxtDrawer v-if="$slots.filters" v-model:open="filtersOpen" :title="'Filtros: ' + title" description="Recortes desta tela.">
      <template #title><div class="flex w-full items-center gap-2"><span class="flex-1">Filtros</span><NuxtButton icon="i-lucide-x" square aria-label="Fechar filtros" variant="ghost" color="neutral" class="size-11 justify-center" @click="filtersOpen = false" /></div></template>
      <template #body><div class="flex flex-col gap-3"><slot name="filters" :close="() => (filtersOpen = false)" /></div></template>
      <template #footer><div class="flex gap-2"><NuxtButton label="Limpar" color="neutral" variant="ghost" class="min-h-11" :disabled="!filterActive" @click="emit('clear')" /><NuxtButton label="Ver resultados" class="min-h-11 flex-1 justify-center" @click="filtersOpen = false" /></div></template>
    </NuxtDrawer>
  </div>
</template>
