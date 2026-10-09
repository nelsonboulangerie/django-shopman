<script setup lang="ts">
// Protótipo da `OperatorTable` (K1), rodada 2. Tudo é a `NuxtTable` oficial (TanStack):
// ordenação no cabeçalho, busca integrada (`global-filter`), linha expansível, seleção,
// colunas. Decisões do dono (09/10):
//   - COMPACTA é o padrão; "Confortável" é a alternância, guardada por dispositivo
//     (`localStorage`, lido depois de montar para o servidor e o cliente concordarem);
//   - a linha expandida NÃO compacta: o conteúdo aberto ganha o respiro da confortável;
//   - a barra de seleção ocupa o lugar da toolbar da tela (quem desenha a toolbar é a
//     tela; a tabela só entrega a seleção por `v-model`).
// No celular, as colunas de apoio somem por CSS (`max-sm:hidden` no `meta.class` da
// coluna), nunca por media query em JS; o nome do cliente quebra, nunca corta.
import { computed } from "vue";

import { brl } from "../data/fase2";
import type { Fase2Order } from "../types/fase2";

const props = withDefaults(
  defineProps<{
    rows: readonly Fase2Order[];
    density?: "compact" | "comfortable";
    /** O pedido aberto no detalhe ao lado: a linha fica marcada. */
    activeRef?: string;
    caption: string;
  }>(),
  { density: "compact", activeRef: "" },
);
const emit = defineEmits<{ open: [ref: string] }>();
const globalFilter = defineModel<string>("globalFilter", { default: "" });
const rowSelection = defineModel<Record<string, boolean>>("rowSelection", { default: () => ({}) });
const expanded = defineModel<Record<string, boolean>>("expanded", { default: () => ({}) });
const columnVisibility = defineModel<Record<string, boolean>>("columnVisibility", { default: () => ({}) });
const sorting = defineModel<{ id: string; desc: boolean }[]>("sorting", { default: () => [{ id: "ref", desc: true }] });

const phoneHidden = { th: "max-sm:hidden", td: "max-sm:hidden" };
const end = { th: "text-end", td: "text-end" };
const columns = [
  { id: "select", enableHiding: false, enableSorting: false },
  { id: "expand", enableHiding: false, enableSorting: false, meta: { class: phoneHidden } },
  { accessorKey: "ref", header: "Pedido", enableHiding: false },
  { accessorKey: "date", header: "Dia", meta: { class: phoneHidden } },
  { accessorKey: "customer", header: "Cliente" },
  { accessorKey: "channel", header: "Canal", meta: { class: phoneHidden } },
  { accessorKey: "payment", header: "Pagamento", meta: { class: phoneHidden } },
  { accessorKey: "stage", header: "Situação", meta: { class: phoneHidden } },
  { accessorKey: "total_q", header: "Total", meta: { class: end } },
  { id: "actions", enableHiding: false, enableSorting: false },
];
const sortable = ["ref", "date", "customer", "total_q"] as const;
const labels: Record<string, string> = {
  ref: "Pedido",
  date: "Dia",
  customer: "Cliente",
  channel: "Canal",
  payment: "Pagamento",
  stage: "Situação",
  total_q: "Total",
};

// Compacta = a linha baixa; a confortável é a do Nuxt UI. O `:ui` mora aqui, uma vez.
const densityUi = computed(() => ({
  th: props.density === "compact" ? "px-2 py-1 text-sm" : "px-4 py-3.5 text-sm",
  td: props.density === "compact" ? "px-2 py-1 text-sm whitespace-normal" : "px-4 py-3 text-sm whitespace-normal",
  tr: "data-[expanded=true]:bg-elevated/50",
}));
// A linha aberta mantém o respiro da confortável na compacta (px-4 py-3 no total).
const expandedPad = computed(() => (props.density === "compact" ? "px-2 py-2" : ""));

const meta = computed(() => ({
  class: {
    tr: (row: { original: Fase2Order }) =>
      row.original.ref === props.activeRef ? "bg-elevated outline-2 -outline-offset-2 outline-primary" : "",
  },
}));

function rowActions(order: Fase2Order) {
  return [
    [{ label: "Abrir o pedido", icon: "i-lucide-panel-right-open", onSelect: () => emit("open", order.ref) }],
    [
      { label: "Imprimir as vias", icon: "i-lucide-printer" },
      { label: "Copiar o código", icon: "i-lucide-copy" },
    ],
  ];
}

const stageColor = (stage: Fase2Order["stage"]) =>
  stage === "Atrasado" || stage === "Cancelado" ? "error" : stage === "Novo" ? "primary" : "neutral";

const sortIcon = (state: false | "asc" | "desc") =>
  state === "asc" ? "i-lucide-arrow-up" : state === "desc" ? "i-lucide-arrow-down" : "i-lucide-arrow-up-down";
const sortLabel = (name: string, state: false | "asc" | "desc") =>
  state === "asc"
    ? `${name}, em ordem crescente. Tocar inverte`
    : state === "desc"
      ? `${name}, em ordem decrescente. Tocar inverte`
      : `Ordenar por ${name.toLowerCase()}`;
</script>

<template>
  <NuxtTable
    v-model:sorting="sorting"
    v-model:global-filter="globalFilter"
    v-model:expanded="expanded"
    v-model:row-selection="rowSelection"
    v-model:column-visibility="columnVisibility"
    :data="props.rows"
    :columns="columns"
    :meta="meta"
    :get-row-id="(row: Fase2Order) => row.ref"
    :ui="densityUi"
    :caption="caption"
    :data-density="density"
    data-fase2-table
    @select="(_event: Event, row: { original: Fase2Order }) => emit('open', row.original.ref)"
  >
    <template #select-header="{ table }">
      <NuxtCheckbox
        :model-value="table.getIsSomePageRowsSelected() ? 'indeterminate' : table.getIsAllPageRowsSelected()"
        aria-label="Selecionar todos os pedidos da tabela"
        @update:model-value="(value: boolean | 'indeterminate') => table.toggleAllPageRowsSelected(!!value)"
      />
    </template>
    <template #select-cell="{ row }">
      <span @click.stop>
        <NuxtCheckbox
          :model-value="row.getIsSelected()"
          :aria-label="`Selecionar o pedido ${row.original.ref}`"
          @update:model-value="(value: boolean | 'indeterminate') => row.toggleSelected(!!value)"
        />
      </span>
    </template>
    <template #expand-cell="{ row }">
      <NuxtButton
        :icon="row.getIsExpanded() ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
        color="neutral"
        variant="ghost"
        square
        :aria-label="`Itens do pedido ${row.original.ref}`"
        :aria-expanded="row.getIsExpanded()"
        @click.stop="row.toggleExpanded()"
      />
    </template>
    <template v-for="key in sortable" :key="key" #[`${key}-header`]="{ column }">
      <NuxtButton
        :label="labels[key]"
        :trailing-icon="sortIcon(column.getIsSorted())"
        color="neutral"
        variant="ghost"
        class="-mx-2.5"
        :class="key === 'total_q' ? 'ms-auto' : ''"
        :aria-label="sortLabel(labels[key] ?? key, column.getIsSorted())"
        @click="column.toggleSorting(column.getIsSorted() === 'asc')"
      />
    </template>
    <template #ref-cell="{ row }">
      <span class="font-semibold tabular-nums text-highlighted">{{ row.original.ref }}</span>
    </template>
    <template #date-cell="{ row }">
      <span class="tabular-nums">{{ row.original.date }} {{ row.original.eta }}</span>
    </template>
    <template #customer-cell="{ row }">
      <span class="block min-w-28">{{ row.original.customer }}</span>
    </template>
    <template #stage-cell="{ row }">
      <NuxtBadge :color="stageColor(row.original.stage)" :label="row.original.stage" />
    </template>
    <template #total_q-cell="{ row }">
      <span class="tabular-nums">{{ brl(row.original.total_q) }}</span>
    </template>
    <template #actions-cell="{ row }">
      <span @click.stop>
        <NuxtDropdownMenu :items="rowActions(row.original)" :content="{ align: 'end' }">
          <NuxtButton
            icon="i-lucide-ellipsis"
            color="neutral"
            variant="ghost"
            square
            :aria-label="`Mais ações do pedido ${row.original.ref}`"
          />
        </NuxtDropdownMenu>
      </span>
    </template>
    <template #expanded="{ row }">
      <div :class="expandedPad" class="grid gap-3 sm:grid-cols-[1fr_auto]" data-fase2-expanded>
        <ul class="space-y-1 text-sm text-default" :aria-label="`Itens do pedido ${row.original.ref}`">
          <li v-for="item in row.original.items" :key="item">{{ item }}</li>
        </ul>
        <p class="text-sm text-muted">{{ row.original.channel }} · {{ row.original.payment }}</p>
      </div>
    </template>
  </NuxtTable>
</template>
