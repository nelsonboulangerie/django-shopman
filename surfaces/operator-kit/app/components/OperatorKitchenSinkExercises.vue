<script setup lang="ts">
import { computed, h, ref, resolveComponent, shallowRef } from "vue";
import { CalendarDate } from "@internationalized/date";
import type { TableColumn } from "@nuxt/ui";
import { getPaginationRowModel } from "@tanstack/vue-table";

// Exercícios do catálogo. As alternativas não são novos tokens ou wrappers.
const cardVariants = ["outline", "soft", "subtle", "solid"] as const;
const badgeVariants = ["solid", "outline", "soft", "subtle"] as const;
const badgeColors = [
  "primary",
  "neutral",
  "success",
  "warning",
  "error",
  "info",
] as const;
const groupVariants = ["list", "card", "table"] as const;
const choices = [
  { label: "Retirada", value: "pickup", description: "Entrega no balcão" },
  { label: "Entrega", value: "delivery", description: "Entrega no endereço" },
  { label: "Indisponível", value: "disabled", disabled: true },
];
const channels = ref(["pickup"]);
const channel = ref("pickup");
const selected = ref("pickup");
const searched = ref("pickup");
const date = shallowRef(new CalendarDate(2026, 10, 6));
const range = shallowRef({
  start: new CalendarDate(2026, 10, 6),
  end: new CalendarDate(2026, 10, 12),
});
const filter = ref("");
const page = ref(1);
const rowSelection = ref({});
const expanded = ref({});
const sorting = ref([{ id: "amount", desc: true }]);
const table = ref();
type Order = { ref: string; customer: string; status: string; amount: number };
const rows = ref<Order[]>(
  Array.from({ length: 12 }, (_, index) => ({
    ref: `PED-${String(index + 1).padStart(3, "0")}`,
    customer: ["Ana Silva", "João Santos", "Maria Oliveira"][index % 3]!,
    status: index % 3 === 0 ? "Em preparo" : "Pronto",
    amount: 1800 + index * 350,
  })),
);
const visibleRows = computed(() =>
  rows.value.filter((row) =>
    `${row.ref} ${row.customer} ${row.status}`
      .toLocaleLowerCase()
      .includes(filter.value.toLocaleLowerCase()),
  ),
);
const money = (value: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    value / 100,
  );
const Button = resolveComponent("NuxtButton");
const Checkbox = resolveComponent("NuxtCheckbox");
const Badge = resolveComponent("NuxtBadge");
const columns: TableColumn<Order>[] = [
  {
    id: "select",
    footer: () => h("span", { class: "sr-only" }, "Seleção"),
    header: ({ table: api }) =>
      h(Checkbox, {
        modelValue: api.getIsAllPageRowsSelected(),
        "onUpdate:modelValue": (value: boolean) =>
          api.toggleAllPageRowsSelected(value),
        "aria-label": "Selecionar pedidos da página",
      }),
    cell: ({ row }) =>
      h(Checkbox, {
        modelValue: row.getIsSelected(),
        "onUpdate:modelValue": (value: boolean) => row.toggleSelected(value),
        "aria-label": `Selecionar ${row.original.ref}`,
      }),
  },
  {
    id: "expand",
    header: () => h("span", { class: "sr-only" }, "Detalhes"),
    footer: () => h("span", { class: "sr-only" }, "Detalhes"),
    cell: ({ row }) =>
      h(Button, {
        icon: row.getIsExpanded()
          ? "i-lucide-chevron-up"
          : "i-lucide-chevron-down",
        color: "neutral",
        variant: "ghost",
        "aria-label": `Detalhes de ${row.original.ref}`,
        "aria-expanded": row.getIsExpanded(),
        onClick: () => row.toggleExpanded(),
      }),
  },
  { accessorKey: "ref", header: "Pedido", footer: "Total filtrado" },
  {
    accessorKey: "customer",
    header: "Cliente",
    footer: () => h("span", { class: "sr-only" }, "Clientes"),
  },
  {
    accessorKey: "status",
    header: "Estado",
    footer: () => h("span", { class: "sr-only" }, "Estados"),
    cell: ({ row }) =>
      h(
        Badge,
        {
          color: row.original.status === "Pronto" ? "success" : "warning",
          variant: "soft",
        },
        () => row.original.status,
      ),
  },
  {
    accessorKey: "amount",
    header: ({ column }) =>
      h(Button, {
        label: "Valor",
        icon: "i-lucide-arrow-up-down",
        color: "neutral",
        variant: "ghost",
        onClick: () => column.toggleSorting(column.getIsSorted() === "asc"),
      }),
    cell: ({ row }) => money(row.original.amount),
    footer: () =>
      money(visibleRows.value.reduce((total, row) => total + row.amount, 0)),
  },
];
const surfaces = [
  { name: "default", token: "--ui-bg", css: "bg-default" },
  { name: "muted", token: "--ui-bg-muted", css: "bg-muted" },
  { name: "elevated", token: "--ui-bg-elevated", css: "bg-elevated" },
  { name: "accented", token: "--ui-bg-accented", css: "bg-accented" },
  {
    name: "inverted",
    token: "--ui-bg-inverted",
    css: "bg-inverted text-inverted",
  },
];
let settle: (() => void) | undefined;
const { run: save, pending } = usePendingAction(
  () =>
    new Promise<void>((resolve) => {
      settle = resolve;
    }),
);
function finish() {
  settle?.();
  settle = undefined;
}
const connectivity = useConnectivity();
const dragged = ref<string>();
const priority = ref(["PED-001", "PED-002", "PED-003"]);
function move(index: number, delta: number) {
  const next = index + delta;
  if (next < 0 || next >= priority.value.length) return;
  const item = priority.value.splice(index, 1)[0]!;
  priority.value.splice(next, 0, item);
}
function drop(target: string) {
  const source = priority.value.indexOf(dragged.value || "");
  const destination = priority.value.indexOf(target);
  if (source >= 0 && destination >= 0) move(source, destination - source);
  dragged.value = undefined;
}
</script>

<template>
  <section
    id="visual-exercises"
    class="space-y-5"
    aria-labelledby="exercise-title"
  >
    <div>
      <h2 id="exercise-title" class="op-title">Laboratório de composição</h2>
      <p class="op-body text-muted">
        Alternativas para decidir. Mesmos dados, componentes Nuxt UI e tokens do
        kit.
      </p>
    </div>
    <NuxtAlert
      title="Propostas visuais"
      description="Escolha hierarquia de cards e distribuição das ações. Estes exercícios não tornam todas as combinações um padrão da suíte."
      variant="soft"
      color="info"
    />

    <NuxtCard
      title="Design system e tema"
      description="Papéis oficiais do Nuxt UI ligados aos tokens do operator-kit"
    >
      <template #header
        ><div class="flex items-center justify-between gap-2">
          <h3 class="op-title">Tema, superfícies e texto</h3>
          <NuxtColorModeButton aria-label="Alternar tema" /></div
      ></template>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <div
          v-for="surface in surfaces"
          :key="surface.name"
          class="rounded-md border border-default p-3"
          :class="surface.css"
        >
          <p class="op-label">{{ surface.name }}</p>
          <code class="op-micro break-all">{{ surface.token }}</code>
        </div>
      </div>
      <div class="mt-3 flex flex-wrap gap-3">
        <span class="text-dimmed">dimmed</span
        ><span class="text-muted">muted</span
        ><span class="text-toned">toned</span
        ><span class="text-default">default</span
        ><span class="text-highlighted">highlighted</span>
      </div>
      <p class="op-micro mt-3">
        Instrument Sans. Tokens de cor, borda, raio e espaçamento vêm da layer.
        As apps compõem variantes e slots oficiais.
      </p>
    </NuxtCard>
    <NuxtCard
      title="Composables operacionais"
      description="Estado real e comportamento compartilhado, com conclusão controlada da fixture"
    >
      <div class="flex flex-wrap items-center gap-2">
        <NuxtButton :loading="pending" @click="save()"
          >Salvar exemplo</NuxtButton
        ><NuxtButton
          :disabled="!pending"
          color="neutral"
          variant="outline"
          @click="finish()"
          >Concluir resposta simulada</NuxtButton
        >
      </div>
      <p class="op-body mt-3">
        usePendingAction impede envio repetido e mantém o estado pendente até a
        resposta. A conectividade abaixo é do dispositivo, não do cenário
        simulado.
      </p>
      <NuxtBadge
        class="mt-2"
        :color="connectivity.isOnline.value ? 'success' : 'warning'"
        variant="soft"
        >{{
          connectivity.isOnline.value
            ? "Dispositivo online"
            : "Dispositivo offline"
        }}</NuxtBadge
      >
    </NuxtCard>

    <h3 class="op-title">Cards, contraste e profundidade</h3>
    <div class="grid gap-3 lg:grid-cols-3">
      <NuxtCard
        title="A. Branco e borda"
        description="Plano pai discreto, conteúdo interno branco"
        variant="soft"
      >
        <NuxtCard
          title="Pedido confirmado"
          description="O card interno é a unidade de trabalho"
          variant="outline"
          class="bg-card"
          ><NuxtBadge color="success" variant="soft"
            >Pronto</NuxtBadge
          ></NuxtCard
        >
      </NuxtCard>
      <NuxtCard
        title="B. Branco e superfície suave"
        description="Hierarquia pela superfície, sem sombra"
        variant="outline"
        class="bg-card"
      >
        <NuxtCard
          title="Pedido confirmado"
          description="Bloco interno subordinado"
          variant="soft"
          ><NuxtBadge color="success" variant="outline"
            >Pronto</NuxtBadge
          ></NuxtCard
        >
      </NuxtCard>
      <NuxtCard
        title="C. Elevação discreta"
        description="Sombra apenas na unidade interna"
        variant="outline"
      >
        <NuxtCard
          title="Pedido confirmado"
          description="Compare se a sombra esclarece ou pesa"
          variant="outline"
          class="bg-card shadow-sm"
          ><NuxtBadge color="success" variant="subtle"
            >Pronto</NuxtBadge
          ></NuxtCard
        >
      </NuxtCard>
    </div>
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <NuxtCard
        v-for="variant in cardVariants"
        :key="variant"
        :variant="variant"
        :title="variant"
        description="Mesma informação, tratamento canônico"
        ><p class="op-figure">R$ 48,50</p></NuxtCard
      >
    </div>
    <NuxtPageCard
      title="Destaque semântico"
      description="Atenção à próxima decisão, sem nova paleta"
      icon="i-lucide-triangle-alert"
      highlight
      highlight-color="warning"
      variant="outline"
      ><p>Dois pedidos precisam de revisão.</p></NuxtPageCard
    >

    <h3 class="op-title">Ações e espaço disponível</h3>
    <div class="grid gap-3 lg:grid-cols-3">
      <NuxtCard
        title="A. Principal ocupa a linha"
        description="Uma decisão principal, alternativa discreta"
      >
        <div class="space-y-2">
          <NuxtButton block>Confirmar recebimento</NuxtButton
          ><NuxtButton block color="neutral" variant="ghost">Voltar</NuxtButton>
        </div>
      </NuxtCard>
      <NuxtCard
        title="B. Um terço e dois terços"
        description="Alternativa visível sem igualar importância"
      >
        <div class="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2">
          <NuxtButton block color="neutral" variant="outline">Voltar</NuxtButton
          ><NuxtButton block class="whitespace-normal text-center"
            >Confirmar recebimento</NuxtButton
          >
        </div>
      </NuxtCard>
      <NuxtCard
        title="C. Largura pelo conteúdo"
        description="Desktop compacto, mobile com ação estável"
      >
        <div class="flex flex-wrap justify-end gap-2">
          <NuxtButton color="neutral" variant="outline">Voltar</NuxtButton
          ><NuxtButton>Confirmar</NuxtButton>
        </div>
      </NuxtCard>
    </div>

    <h3 class="op-title">Badges: semântica, cor e ênfase</h3>
    <NuxtAlert
      variant="solid"
      color="primary"
      title="Operação confirmada"
      description="Título e descrição preservam contraste sobre fundo sólido."
    />
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <NuxtCard v-for="variant in badgeVariants" :key="variant" :title="variant"
        ><div class="flex flex-wrap gap-2">
          <NuxtBadge
            v-for="color in badgeColors"
            :key="color"
            :color="color"
            :variant="variant"
            >{{ color }}</NuxtBadge
          >
        </div></NuxtCard
      >
    </div>

    <h3 class="op-title">Escolhas e menus</h3>
    <div class="grid gap-3 lg:grid-cols-3">
      <NuxtCard
        v-for="variant in groupVariants"
        :key="variant"
        :title="variant"
      >
        <NuxtCheckboxGroup
          v-model="channels"
          :items="choices"
          :variant="variant"
          legend="Canais disponíveis"
        />
        <NuxtSeparator class="my-4" />
        <NuxtRadioGroup
          v-model="channel"
          :items="choices"
          :variant="variant"
          legend="Canal deste pedido"
        />
      </NuxtCard>
    </div>
    <NuxtCard
      title="Select e SelectMenu"
      description="Menus renderizados pelo Nuxt UI, com teclado, busca e item indisponível"
    >
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Select"
          ><NuxtSelect
            v-model="selected"
            :items="choices"
            class="w-full"
            aria-label="Canal por select" /></NuxtFormField
        ><NuxtFormField label="SelectMenu com busca"
          ><NuxtSelectMenu
            v-model="searched"
            :items="choices"
            value-key="value"
            class="w-full"
            aria-label="Buscar canal"
        /></NuxtFormField>
      </div>
    </NuxtCard>

    <h3 class="op-title">Calendários operacionais</h3>
    <div class="grid gap-3 lg:grid-cols-2">
      <NuxtCard title="Data de retirada"
        ><NuxtCalendar
          v-model="date"
          locale="pt-BR"
          aria-label="Data de retirada"
      /></NuxtCard>
      <NuxtCard title="Período de análise"
        ><NuxtCalendar
          v-model="range"
          range
          locale="pt-BR"
          aria-label="Período de análise"
      /></NuxtCard>
    </div>

    <NuxtCard
      title="Tabela operacional"
      description="Seleção, detalhes expansíveis, badges, ordenação, filtro, total e paginação"
      :ui="{ root: 'overflow-visible', body: 'p-0 sm:p-0' }"
    >
      <template #header
        ><div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="op-title">Pedidos</h3>
          <NuxtInput
            v-model="filter"
            placeholder="Filtrar pedidos"
            aria-label="Filtrar pedidos"
            @update:model-value="page = 1"
          /></div
      ></template>
      <div
        class="max-h-96 overflow-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
        data-operator-overflow="horizontal"
        tabindex="0"
        role="region"
        aria-label="Tabela com rolagem externa"
      >
        <NuxtTable
          ref="table"
          v-model:row-selection="rowSelection"
          v-model:expanded="expanded"
          v-model:sorting="sorting"
          :pagination="{ pageIndex: page - 1, pageSize: 4 }"
          :pagination-options="{
            getPaginationRowModel: getPaginationRowModel(),
          }"
          :data="visibleRows"
          :get-row-id="(row) => row.ref"
          :columns="columns"
          sticky="header"
          :ui="{ root: 'overflow-visible' }"
          aria-label="Pedidos do laboratório"
        >
          <template #expanded="{ row }"
            ><div class="p-3">
              <p class="op-label">{{ row.original.ref }}: retirada no balcão</p>
              <p class="op-body">
                Pagamento confirmado. Dois itens. Detalhes acessíveis sem sair
                da fila.
              </p>
            </div></template
          >
        </NuxtTable>
      </div>
      <template #footer
        ><div class="flex flex-wrap items-center justify-between gap-2">
          <p class="op-micro">
            {{ Object.keys(rowSelection).length }} selecionados. Total dos
            pedidos filtrados no rodapé da coluna.
          </p>
          <NuxtPagination
            v-model:page="page"
            :show-edges="false"
            :sibling-count="0"
            :total="visibleRows.length"
            :items-per-page="4"
          /></div
      ></template>
    </NuxtCard>
    <NuxtCard
      title="Prioridade reordenável"
      description="Arraste pelo mouse ou use os botões pelo teclado e toque. Esta ordem é manual, separada da tabela ordenada por valor."
    >
      <div class="space-y-2">
        <div
          v-for="(item, index) in priority"
          :key="item"
          draggable="true"
          class="flex items-center gap-2 rounded-md border border-default p-2"
          @dragstart="dragged = item"
          @dragover.prevent
          @drop.prevent="drop(item)"
        >
          <NuxtIcon name="i-lucide-grip-vertical" /><span class="flex-1">{{
            item
          }}</span
          ><NuxtButton
            icon="i-lucide-arrow-up"
            color="neutral"
            variant="ghost"
            :disabled="index === 0"
            :aria-label="`Subir ${item}`"
            @click="move(index, -1)"
          /><NuxtButton
            icon="i-lucide-arrow-down"
            color="neutral"
            variant="ghost"
            :disabled="index === priority.length - 1"
            :aria-label="`Descer ${item}`"
            @click="move(index, 1)"
          />
        </div>
      </div>
    </NuxtCard>
  </section>
</template>
