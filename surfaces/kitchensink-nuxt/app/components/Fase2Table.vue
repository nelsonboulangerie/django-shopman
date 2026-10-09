<script setup lang="ts">
// Protótipo da `OperatorTable` (K1) com a `OperatorBulkBar` (K2). Tudo é a `NuxtTable`
// oficial (TanStack): ordenação pelo cabeçalho (`v-model:sorting`), busca integrada
// (`v-model:global-filter`), linha expansível (`v-model:expanded`), seleção
// (`v-model:row-selection`) e colunas (`v-model:column-visibility`). O que o Nuxt UI
// não tem é a DENSIDADE: o `:ui` dela mora aqui, uma vez, que é onde a peça nasceria no
// kit (pergunta 1 ao dono). Texto da casa (o nome do cliente) quebra, nunca corta.
import type { Fase2Order } from "../types/fase2";
import { computed, ref } from "vue";


const props = defineProps<{ rows: readonly Fase2Order[] }>();
const density = defineModel<"comfortable" | "compact">("density", { default: "comfortable" });

const brl = (q: number) => (q / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const columns = [
  { id: "select", enableHiding: false, enableSorting: false },
  { id: "expand", enableHiding: false, enableSorting: false },
  { accessorKey: "ref", header: "Pedido", enableHiding: false },
  { accessorKey: "customer", header: "Cliente" },
  { accessorKey: "channel", header: "Canal" },
  { accessorKey: "stage", header: "Situação" },
  { accessorKey: "total_q", header: "Total" },
  { accessorKey: "eta", header: "Previsto" },
  { id: "actions", enableHiding: false, enableSorting: false },
];
const sortable = ["ref", "customer", "total_q", "eta"] as const;
const labels: Record<string, string> = {
  ref: "Pedido",
  customer: "Cliente",
  channel: "Canal",
  stage: "Situação",
  total_q: "Total",
  eta: "Previsto",
};

const sorting = ref([{ id: "eta", desc: false }]);
const globalFilter = ref("");
const expanded = ref<Record<string, boolean>>({});
const rowSelection = ref<Record<string, boolean>>({});
const columnVisibility = ref<Record<string, boolean>>({ channel: true });

const selectedRefs = computed(() => Object.keys(rowSelection.value).filter((key) => rowSelection.value[key]));
const selectedCount = computed(() => selectedRefs.value.length);
function clearSelection() {
  rowSelection.value = {};
}

const columnItems = computed(() =>
  ["customer", "channel", "stage", "total_q", "eta"].map((id) => ({
    label: labels[id],
    type: "checkbox" as const,
    checked: columnVisibility.value[id] !== false,
    onUpdateChecked: (checked: boolean) => {
      columnVisibility.value = { ...columnVisibility.value, [id]: checked };
    },
    onSelect: (event: Event) => event.preventDefault(),
  })),
);

function rowActions(order: Fase2Order) {
  return [
    [{ label: "Abrir o pedido", icon: "i-lucide-external-link" }],
    [
      { label: "Aceitar", icon: "i-lucide-check" },
      { label: "Copiar o código", icon: "i-lucide-copy" },
    ],
    [{ label: `Recusar ${order.ref}`, icon: "i-lucide-x", color: "error" as const }],
  ];
}

const stageColor = (stage: Fase2Order["stage"]) =>
  stage === "Atrasado" ? "error" : stage === "Pronto" ? "success" : stage === "Novo" ? "primary" : "neutral";

const densityUi = computed(() =>
  density.value === "compact"
    ? { th: "px-2 py-1.5 text-xs", td: "px-2 py-1 text-sm" }
    : { th: "px-4 py-3.5 text-sm", td: "px-4 py-3 text-sm" },
);

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
  <NuxtCard class="min-w-0" :ui="{ body: 'p-0 sm:p-0' }" data-fase2-table :data-density="density">
    <!-- Toolbar da tabela: OU os recortes da própria tabela, OU a barra de seleção. A
         seleção ocupa o lugar da toolbar na mesa (pergunta 3, opção 1) e vira a ação
         na base no celular. -->
    <div class="border-b border-default">
      <OperatorToolbar v-if="!selectedCount" data-fase2-table-toolbar>
        <template #left>
          <NuxtInput
            v-model="globalFilter"
            icon="i-lucide-search"
            placeholder="Filtrando estes pedidos"
            aria-label="Filtrar os pedidos desta tabela"
            class="w-40 sm:w-64"
          />
        </template>
        <template #right>
          <NuxtFieldGroup>
            <NuxtButton
              label="Confortável"
              color="neutral"
              variant="outline"
              :active="density === 'comfortable'"
              active-variant="solid"
              @click="density = 'comfortable'"
            />
            <NuxtButton
              label="Compacta"
              color="neutral"
              variant="outline"
              :active="density === 'compact'"
              active-variant="solid"
              @click="density = 'compact'"
            />
          </NuxtFieldGroup>
          <NuxtDropdownMenu :items="columnItems" :content="{ align: 'end' }">
            <NuxtButton label="Colunas" icon="i-lucide-columns-3" color="neutral" variant="outline" />
          </NuxtDropdownMenu>
        </template>
      </OperatorToolbar>
      <OperatorToolbar v-else data-fase2-bulk-bar>
        <template #left>
          <span class="text-sm font-semibold" aria-live="polite">{{ selectedCount }} selecionados</span>
          <NuxtButton label="Limpar seleção" color="neutral" variant="ghost" @click="clearSelection" />
        </template>
        <template #right>
          <NuxtButton label="Avançar" icon="i-lucide-arrow-right" color="neutral" variant="outline" class="max-sm:hidden" />
          <NuxtButton :label="`Aceitar ${selectedCount}`" icon="i-lucide-check" class="max-sm:hidden" />
        </template>
      </OperatorToolbar>
    </div>

    <NuxtTable
      v-model:sorting="sorting"
      v-model:global-filter="globalFilter"
      v-model:expanded="expanded"
      v-model:row-selection="rowSelection"
      v-model:column-visibility="columnVisibility"
      :data="props.rows"
      :columns="columns"
      :get-row-id="(row: Fase2Order) => row.ref"
      :ui="densityUi"
      caption="Pedidos em andamento (exemplo)"
      sticky="header"
      class="max-h-120"
    >
      <template #select-header="{ table }">
        <NuxtCheckbox
          :model-value="table.getIsSomePageRowsSelected() ? 'indeterminate' : table.getIsAllPageRowsSelected()"
          aria-label="Selecionar todos os pedidos da tabela"
          @update:model-value="(value: boolean | 'indeterminate') => table.toggleAllPageRowsSelected(!!value)"
        />
      </template>
      <template #select-cell="{ row }">
        <NuxtCheckbox
          :model-value="row.getIsSelected()"
          :aria-label="`Selecionar o pedido ${row.original.ref}`"
          @update:model-value="(value: boolean | 'indeterminate') => row.toggleSelected(!!value)"
        />
      </template>
      <template #expand-cell="{ row }">
        <NuxtButton
          :icon="row.getIsExpanded() ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
          color="neutral"
          variant="ghost"
          square
          :aria-label="`Itens do pedido ${row.original.ref}`"
          :aria-expanded="row.getIsExpanded()"
          @click="row.toggleExpanded()"
        />
      </template>
      <template v-for="key in sortable" :key="key" #[`${key}-header`]="{ column }">
        <NuxtButton
          :label="labels[key]"
          :trailing-icon="sortIcon(column.getIsSorted())"
          color="neutral"
          variant="ghost"
          class="-mx-2.5"
          :aria-label="sortLabel(labels[key] ?? key, column.getIsSorted())"
          @click="column.toggleSorting(column.getIsSorted() === 'asc')"
        />
      </template>
      <template #ref-cell="{ row }">
        <span class="font-semibold tabular-nums">{{ row.original.ref }}</span>
      </template>
      <template #customer-cell="{ row }">
        <span class="block min-w-32 whitespace-normal">{{ row.original.customer }}</span>
      </template>
      <template #stage-cell="{ row }">
        <NuxtBadge :color="stageColor(row.original.stage)" :label="row.original.stage" />
      </template>
      <template #total_q-cell="{ row }">
        <span class="tabular-nums">{{ brl(row.original.total_q) }}</span>
      </template>
      <template #eta-cell="{ row }">
        <span class="tabular-nums">{{ row.original.eta }}</span>
      </template>
      <template #actions-cell="{ row }">
        <NuxtDropdownMenu :items="rowActions(row.original)" :content="{ align: 'end' }">
          <NuxtButton
            icon="i-lucide-ellipsis"
            color="neutral"
            variant="ghost"
            square
            :aria-label="`Mais ações do pedido ${row.original.ref}`"
          />
        </NuxtDropdownMenu>
      </template>
      <template #expanded="{ row }">
        <ul class="space-y-1 text-sm" :aria-label="`Itens do pedido ${row.original.ref}`">
          <li v-for="item in row.original.items" :key="item">{{ item }}</li>
        </ul>
      </template>
    </NuxtTable>

    <!-- Celular: a seleção vira a ação na base (a mesma peça da seção "Ação na base"). -->
    <div v-if="selectedCount" class="sm:hidden">
      <Fase2ActionBar
        context-label="Selecionados"
        :context-value="`${selectedCount} pedidos`"
        :action="`Aceitar ${selectedCount}`"
        secondary="Limpar"
        @secondary="clearSelection"
      />
    </div>
  </NuxtCard>
</template>
