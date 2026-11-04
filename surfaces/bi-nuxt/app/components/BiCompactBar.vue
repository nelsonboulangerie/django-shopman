<script setup lang="ts">
// A linha do chão do B.I. no celular (abaixo de `md`), a mesma do Gestor e da Produção
// (`OperatorCompactBar` do kit): o selo (o app e a seção, abre o trocador), a busca da
// suíte, o sino e o ⋮ no canto com as ações da leitura. A página que a usa se declara
// `data-compact-page`, e o kit esconde nela a barra de cima e a linha de recortes do
// `OperatorPageHeader`; os avisos da tela (`alerts`) seguem logo abaixo.
//
// O B.I. não tem tempo real: o selo não leva ponto de conexão (um "ao vivo" aqui seria
// rótulo que mente). O frescor da leitura segue no painel de cada tela, como já era.
//
// O tempo da leitura (o período, ou o dia na Produção) fica à vista numa faixa logo
// abaixo da linha, como o dia da Produção: trocar o período é o gesto de toda leitura e
// não pode custar ⋮ e Filtros. Os outros recortes vão para "Filtros", dentro do ⋮, e o
// que estiver escolhido aparece na faixa de recorte ativo, com Limpar.
import type {
  OperatorActiveFilter,
  OperatorHeaderAction,
} from "../../../operator-kit/app/presentation/pageHeader";

const props = withDefaults(
  defineProps<{
    /** A seção (o nome da barra lateral), não a pergunta da tela: é o lugar no selo. */
    title: string;
    options?: OperatorHeaderAction[];
    activeFilters?: OperatorActiveFilter[];
    /** O termo da busca da tela, quando ela filtra a própria tabela. */
    query?: string;
    summary?: string;
  }>(),
  { options: () => [], activeFilters: () => [], query: "", summary: "" },
);
const emit = defineEmits<{ clear: [] }>();

const filterLabel = computed(() => props.activeFilters.map((filter) => filter.label).join(", "));
function clear() {
  for (const filter of props.activeFilters) filter.remove();
  emit("clear");
}
</script>

<template>
  <OperatorCompactBar
    :title="title"
    :options="options"
    :query="query"
    :filter-active="activeFilters.length > 0"
    :filter-label="filterLabel"
    :summary="summary"
    @clear="clear"
  >
    <template v-if="$slots.filters" #filters><slot name="filters" /></template>
  </OperatorCompactBar>
  <div
    v-if="$slots.primary"
    class="flex min-h-12 items-center gap-2 overflow-x-auto border-b border-default bg-card px-2 py-1.5 no-scrollbar md:hidden [&>*]:shrink-0"
    data-compact-primary
  >
    <slot name="primary" />
  </div>
</template>
