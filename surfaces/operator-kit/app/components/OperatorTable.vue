<script setup lang="ts" generic="T">
// A tabela da suíte (WP-FASE2-UX-OPERADOR, K1): a `NuxtTable` oficial dentro do cartão
// branco, com o que toda tabela de operador repete e que antes cada tela montava à mão.
//
// - COMPACTA é o padrão (dono, 09/10/2026); Confortável e as colunas visíveis moram no
//   "Exibir" (`OperatorTableView`, na toolbar), guardados por dispositivo pela `view-key`.
// - A linha aberta NÃO compacta: o conteúdo de `#expanded` ganha o respiro da confortável.
// - Ordenação pelo cabeçalho: a coluna que diz `enableSorting: true` ganha o botão.
// - Seleção múltipla (`selectable`), linha expansível (basta o slot `#expanded`), coluna
//   fixada (`pinned`) que cabe no celular, colunas de apoio (`meta.supporting`) que somem
//   no celular por CSS.
// - Carregando, vazio e erro pelo `OperatorScreenState`, com a frase única da suíte.
// - O `:ui` da tabela mora AQUI (a densidade), nunca na tela.
// - Dentro de outro cartão (`in-card`, o quadro de leitura do B.I.), o cartão da tabela é
//   `soft` e o vazio e o carregando perdem a moldura: nunca cartão `outline` em cartão.
//
// Toda célula quebra (`whitespace-normal`): texto da casa nunca é cortado.
import type { TableColumn, TableRow } from "@nuxt/ui";
import { computed, useSlots, watchEffect } from "vue";

import { useOperatorTableView } from "../composables/useOperatorTableView";
import {
  appendClass,
  columnId,
  columnLabel,
  expandedPadding,
  hideableColumns,
  leadWidth,
  OPERATOR_TABLE_DEFAULT_DENSITY,
  PINNED_COLUMN_CLASS,
  sortIcon,
  sortButtonClass,
  sortLabel,
  SUPPORTING_COLUMN_CLASS,
  tableDensityUi,
  type OperatorTableColumnMeta,
} from "../presentation/operatorTable";

const props = withDefaults(
  defineProps<{
    data: readonly T[];
    columns: TableColumn<T>[];
    /** A identidade da linha (seleção, linha aberta, linha ativa). */
    rowKey: (row: T) => string;
    /** O nome da tabela para o leitor de tela ("Pedidos concluídos e cancelados"). */
    caption: string;
    /** A forma neste dispositivo (densidade e colunas): a mesma chave do `OperatorTableView`. */
    viewKey?: string;
    /** Caixa de marcar em cada linha e no cabeçalho. */
    selectable?: boolean;
    /** Como a linha se chama para quem marca ou abre ("o pedido H58"). */
    rowLabel?: (row: T) => string;
    /** A coluna que fica presa à esquerda ao rolar de lado. */
    pinned?: string;
    /** A coluna presa à direita (o ⋯ da linha numa matriz larga). */
    pinnedEnd?: string;
    /** A tabela ocupa a altura que sobra e rola por dentro, com o cabeçalho preso. */
    fill?: boolean;
    /** Classe da linha (estado da tela: arrastando, alvo de soltar). */
    rowClass?: (row: T) => string;
    /** A linha do registro aberto ao lado (detalhe que divide a tela). */
    activeKey?: string;
    /** Abrir a linha (toque ou Enter nela). */
    onSelect?: (row: T, event: Event) => void;
    loading?: boolean;
    error?: boolean;
    /** O que a tabela mostra, com artigo ("o histórico"): a frase do carregando e do erro. */
    what?: string;
    errorDescription?: string;
    emptyTitle?: string;
    emptyDescription?: string;
    emptyIcon?: string;
    /** A tabela mora dentro de outro cartão (o `OperatorReadingCard`): cartão `soft`, vazio sem moldura. */
    inCard?: boolean;
  }>(),
  {
    viewKey: "",
    selectable: false,
    rowLabel: undefined,
    pinned: "",
    pinnedEnd: "",
    fill: false,
    rowClass: undefined,
    activeKey: "",
    onSelect: undefined,
    loading: false,
    error: false,
    what: "",
    errorDescription: "",
    emptyTitle: "",
    emptyDescription: "",
    emptyIcon: "i-lucide-inbox",
    inCard: false,
  },
);

const emit = defineEmits<{ retry: [] }>();
// Atributos (`data-*`, `sticky`, `class`) vão para a tabela, não para o invólucro.
defineOptions({ inheritAttrs: false });

const sorting = defineModel<{ id: string; desc: boolean }[]>("sorting", { default: () => [] });
const rowSelection = defineModel<Record<string, boolean>>("rowSelection", { default: () => ({}) });
const expanded = defineModel<Record<string, boolean>>("expanded", { default: () => ({}) });
const globalFilter = defineModel<string>("globalFilter", { default: "" });

const slots = useSlots();
const view = props.viewKey ? useOperatorTableView(props.viewKey) : null;
const density = computed(() => view?.density.value ?? OPERATOR_TABLE_DEFAULT_DENSITY);
const visibility = computed(() => view?.visibility.value ?? {});

// O "Exibir" lista as colunas que podem sumir sem a tela repetir a lista: a chave e a
// coluna fixada ficam de fora.
watchEffect(() => {
  if (!view) return;
  view.columns.value = hideableColumns(props.columns as never[]).filter(
    (column) => column.id !== props.pinned && column.id !== props.pinnedEnd,
  );
});

const hasExpanded = computed(() => Boolean(slots.expanded));
const label = (row: T) => props.rowLabel?.(row) ?? `a linha ${props.rowKey(row)}`;

type Meta = OperatorTableColumnMeta & { class?: { th?: unknown; td?: unknown } };

const tableColumns = computed<TableColumn<T>[]>(() => {
  const lead: TableColumn<T>[] = [];
  // Largura fixa e declarada (`size`): a coluna fixada à direita delas para em
  // `left: soma das larguras`, e o TanStack supõe 150 px para quem não diz.
  const leadColumn = (id: string): TableColumn<T> => {
    const width = leadWidth(id, density.value);
    const style = { width: `${width}px`, minWidth: `${width}px`, maxWidth: `${width}px` };
    return { id, size: width, enableHiding: false, enableSorting: false, meta: { style: { th: style, td: style } } };
  };
  if (props.selectable) lead.push(leadColumn("select"));
  if (hasExpanded.value) lead.push(leadColumn("expand"));
  const own = props.columns.map((column) => {
    const meta = (column.meta ?? {}) as Meta;
    const id = columnId(column as never);
    const extra = [
      meta.supporting ? SUPPORTING_COLUMN_CLASS : "",
      id && id === props.pinned ? PINNED_COLUMN_CLASS : "",
    ]
      .filter(Boolean)
      .join(" ");
    return {
      ...column,
      enableSorting: column.enableSorting === true,
      meta: {
        ...meta,
        class: {
          th: appendClass(meta.class?.th as never, extra),
          td: appendClass(meta.class?.td as never, extra),
        },
      },
    } as TableColumn<T>;
  });
  return [...lead, ...own];
});

const columnPinning = computed(() => ({
  left: props.pinned
    ? [...(props.selectable ? ["select"] : []), ...(hasExpanded.value ? ["expand"] : []), props.pinned]
    : [],
  right: props.pinnedEnd ? [props.pinnedEnd] : [],
}));

// O cabeçalho que ordena: só as colunas que pedem, e só se a tela não desenhou o próprio.
const sortable = computed(() =>
  props.columns
    .filter((column) => column.enableSorting === true)
    .map((column) => ({ id: columnId(column as never), label: columnLabel(column as never) }))
    .filter((column) => !slots[`${column.id}-header`]),
);

// Os slots da tela passam direto à `NuxtTable`; o `#expanded` passa embrulhado no respiro.
const OWN_SLOTS = new Set(["expanded", "footer", "empty-actions"]);
const forwarded = computed(() => Object.keys(slots).filter((name) => !OWN_SLOTS.has(name)));

// Sem pintar a linha aberta: a coluna fixada tem o fundo do cartão (tema), e a linha
// pintada ficava com um retalho branco nela.
const ui = computed(() => tableDensityUi(density.value));
const meta = computed(() => ({
  class: {
    tr: (row: TableRow<T>) =>
      [
        props.rowClass?.(row.original) ?? "",
        props.activeKey && props.rowKey(row.original) === props.activeKey
          ? "bg-elevated outline-2 -outline-offset-2 outline-primary"
          : "",
      ]
        .filter(Boolean)
        .join(" "),
  },
}));

const rows = computed(() => props.data as T[]);
const hasRows = computed(() => props.data.length > 0);
const select = computed(() =>
  props.onSelect ? (event: Event, row: TableRow<T>) => props.onSelect?.(row.original, event) : undefined,
);
</script>

<template>
  <div
    class="min-w-0"
    :class="fill ? 'flex min-h-0 flex-1 flex-col gap-4' : 'space-y-4'"
    data-operator-table-root
  >
    <OperatorScreenState
      v-if="error"
      state="error"
      :what="what"
      :description="errorDescription"
      @retry="emit('retry')"
    />
    <OperatorScreenState v-if="loading && !hasRows" state="loading" :what="what" :in-card="inCard" />
    <!-- Com `fill`, o cartão é uma grade de uma linha para a tabela rolar por dentro. -->
    <NuxtCard
      v-else-if="hasRows"
      :variant="inCard ? 'soft' : 'outline'"
      class="min-w-0"
      :class="fill ? 'grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,1fr)]' : ''"
    >
      <NuxtTable
        v-model:sorting="sorting"
        v-model:row-selection="rowSelection"
        v-model:expanded="expanded"
        v-model:global-filter="globalFilter"
        :data="rows"
        :columns="tableColumns"
        :column-visibility="visibility"
        :column-pinning="columnPinning"
        :get-row-id="(row: T) => rowKey(row)"
        :meta="meta"
        :ui="ui"
        :loading="loading"
        :caption="caption"
        :sticky="fill ? 'header' : undefined"
        :class="fill ? 'h-full' : undefined"
        :on-select="select"
        :data-density="density"
        data-operator-table
        data-operator-overflow="horizontal"
        tabindex="0"
        v-bind="$attrs"
      >
        <template v-if="selectable" #select-header="{ table }">
          <NuxtCheckbox
            :model-value="table.getIsSomeRowsSelected() ? 'indeterminate' : table.getIsAllRowsSelected()"
            :aria-label="`Selecionar todas as linhas de ${caption.toLowerCase()}`"
            data-operator-table-select-all
            @update:model-value="(value: boolean | 'indeterminate') => table.toggleAllRowsSelected(!!value)"
          />
          <span class="sr-only">Seleção</span>
        </template>
        <template v-if="selectable" #select-cell="{ row }">
          <NuxtCheckbox
            :model-value="row.getIsSelected()"
            :aria-label="`Selecionar ${label(row.original)}`"
            data-operator-table-select
            @update:model-value="(value: boolean | 'indeterminate') => row.toggleSelected(!!value)"
          />
        </template>
        <!-- Cabeçalho das colunas de controle: texto para o leitor de tela (axe). -->
        <template v-if="hasExpanded" #expand-header>
          <span class="sr-only">Detalhes</span>
        </template>
        <template v-if="hasExpanded" #expand-cell="{ row }">
          <NuxtButton
            :icon="row.getIsExpanded() ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
            color="neutral"
            variant="ghost"
            square
            :aria-label="`Detalhes de ${label(row.original)}`"
            :aria-expanded="row.getIsExpanded()"
            data-operator-table-expand
            @click="row.toggleExpanded()"
          />
        </template>
        <template v-for="column in sortable" :key="column.id" #[`${column.id}-header`]="{ column: tableColumn }">
          <NuxtButton
            :label="column.label"
            :trailing-icon="sortIcon(tableColumn.getIsSorted())"
            color="neutral"
            variant="ghost"
            :class="sortButtonClass(density)"
            :aria-label="sortLabel(column.label, tableColumn.getIsSorted())"
            :data-operator-table-sort="column.id"
            @click="tableColumn.toggleSorting(tableColumn.getIsSorted() === 'asc')"
          />
        </template>
        <template v-for="name in forwarded" :key="name" #[name]="scope">
          <slot :name="name" v-bind="scope ?? {}" />
        </template>
        <template v-if="hasExpanded" #expanded="scope">
          <div :class="expandedPadding(density)" class="whitespace-normal" data-operator-table-expanded>
            <slot name="expanded" v-bind="scope" />
          </div>
        </template>
      </NuxtTable>
      <template v-if="$slots.footer" #footer>
        <slot name="footer" />
      </template>
    </NuxtCard>
    <OperatorScreenState
      v-else-if="!error"
      state="empty"
      :in-card="inCard"
      :icon="emptyIcon"
      :title="emptyTitle"
      :description="emptyDescription"
    >
      <template v-if="$slots['empty-actions']" #actions><slot name="empty-actions" /></template>
    </OperatorScreenState>
  </div>
</template>
