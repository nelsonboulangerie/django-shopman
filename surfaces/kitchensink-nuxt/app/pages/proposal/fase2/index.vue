<script setup lang="ts">
// Proposta visual da fase 2 (docs/plans/WP-FASE2-UX-OPERADOR.md): as atividades
// comuns do operador desenhadas com peças reais do Nuxt UI e o tema do kit, para o
// dono decidir. Nada aqui é contrato; o que for aprovado nasce no `operator-kit`
// (PRs K0 a K8) e esta página morre junto. O `:ui` só aparece nos protótipos
// `Fase2*`, no lugar onde cada peça nasceria no kit.
import { computed, onMounted, ref } from "vue";

import type { PeriodSelection } from "../../../../../operator-kit/app/presentation/dates";
import type { ActiveFilters, FilterDimension } from "../../../../../operator-kit/app/types/filters";
import type { Fase2Order, QuickFilter, SavedView } from "../../../types/fase2";

useHead({ title: "Proposta: fase 2 da suíte" });

const hydrated = ref(false);
onMounted(() => {
  hydrated.value = true;
});

const questions = [
  {
    id: "densidade",
    title: "1. Densidade da tabela",
    one: "Um botão Compacta / Confortável na tabela, guardado por dispositivo.",
    two: "Compacta sozinha do lg para cima, sem botão.",
    pick: "1",
    why: "a mesma mesa serve ao gestor e ao balcão, e o tablet de toque precisa da confortável.",
    see: "#tabela",
  },
  {
    id: "favoritos",
    title: "2. Favoritos de filtro",
    one: "Cada pessoa tem os seus.",
    two: "Cada pessoa tem os seus, e o gerente pode publicar um para a equipe.",
    pick: "1",
    why: "o modelo já é por pessoa (o do B.I.), e publicar entra depois sem refazer nada.",
    see: "#filtros",
  },
  {
    id: "selecao",
    title: "3. Barra de seleção na mesa",
    one: "Ocupa o lugar da toolbar enquanto houver marcados.",
    two: "Fica na base da tela, como no celular.",
    pick: "1",
    why: "o olho já está na toolbar, e a base de uma tela de 1440 fica longe.",
    see: "#selecao",
  },
] as const;

// ---- barras ---------------------------------------------------------------
const phoneScope = ref("needs");
const phoneScopes: QuickFilter[] = [
  { value: "needs", label: "Precisa de você", count: 5 },
  { value: "all", label: "Todos", count: 18 },
  { value: "late", label: "Atrasados", count: 2 },
];
const deskScope = ref("needs");
const roles = [
  { role: "Barra superior primária", has: "☰, título, Busca, Avisos, ação primária, ⋯", never: "filtros, abas, período, frescor" },
  { role: "Barra superior secundária", has: "filtros rápidos e sub-seções à esquerda; período, Filtros, Favoritos, Colunas à direita; contagem no fim", never: "Atualizar, Exportar, Admin (são ações)" },
  { role: "Barra de seleção", has: "N selecionados, ações em lote, Limpar seleção", never: "filtros" },
  { role: "Aviso da tela", has: "um NuxtAlert; os outros em \"e mais N\"", never: "sem conexão (é do app), aviso com prazo (é o modal)" },
  { role: "Ação na base", has: "contexto + uma ação grande + o motivo quando não pode", never: "navegação; duas ações do mesmo peso" },
  { role: "Barra inferior", has: "3 a 5 seções do app", never: "ação, filtro" },
] as const;

// ---- busca ----------------------------------------------------------------
const searchScope = ref("screen");
const searchScopes = [
  { label: "Esta tela", value: "screen" },
  { label: "Gestor", value: "app" },
  { label: "Toda a suíte", value: "suite" },
];
const searchPlaceholder = computed(
  () =>
    ({
      screen: "Filtrando os pedidos da fila",
      app: "Buscar no Gestor de pedidos",
      suite: "Buscar pedido, cliente, produto ou tela",
    })[searchScope.value] ?? "",
);
const searchGroups = computed(() => {
  const screen = [
    {
      id: "screen",
      label: "Na fila agora",
      items: [
        { label: "1048 · Ana Souza", suffix: "Em preparo", icon: "i-lucide-receipt" },
        { label: "1051 · Bruno Lima", suffix: "Novo", icon: "i-lucide-receipt" },
      ],
    },
  ];
  const app = [
    ...screen,
    {
      id: "history",
      label: "Histórico",
      items: [{ label: "0998 · Ana Souza", suffix: "Retirado ontem", icon: "i-lucide-history" }],
    },
    {
      id: "customers",
      label: "Clientes",
      items: [{ label: "Ana Souza", suffix: "12 pedidos", icon: "i-lucide-user" }],
    },
  ];
  const suite = [
    ...app,
    {
      id: "products",
      label: "Produtos",
      items: [{ label: "Croissant", suffix: "Catálogo", icon: "i-lucide-croissant" }],
    },
    {
      id: "screens",
      label: "Telas",
      items: [{ label: "Fim do dia", suffix: "PDV", icon: "i-lucide-app-window" }],
    },
  ];
  return searchScope.value === "screen" ? screen : searchScope.value === "app" ? app : suite;
});

// ---- filtros --------------------------------------------------------------
const quickValue = ref("needs");
const dimensions: FilterDimension[] = [
  {
    id: "channel",
    label: "Canal",
    type: "multi-select",
    options: [
      { value: "ifood", label: "iFood", count: 7 },
      { value: "site", label: "Site", count: 6 },
      { value: "balcao", label: "Balcão", count: 5 },
    ],
  },
  {
    id: "payment",
    label: "Pagamento",
    type: "multi-select",
    options: [
      { value: "pix", label: "Pix", count: 9 },
      { value: "card", label: "Cartão", count: 8 },
      { value: "cash", label: "Dinheiro", count: 1 },
    ],
  },
  { id: "customer", label: "Cliente", type: "text", options: [], placeholder: "Nome ou telefone" },
];
const filters = ref<ActiveFilters>({ channel: ["ifood"] });
const period = ref<PeriodSelection>({ preset: "day", from: "", to: "" });
const views = ref<SavedView[]>([
  { id: "v1", name: "iFood atrasados", summary: "Atrasados · Canal: iFood", pinned: true },
  { id: "v2", name: "Pix de hoje", summary: "Todos · Pagamento: Pix", pinned: false },
]);
const quickItems = computed<QuickFilter[]>(() => [
  ...phoneScopes,
  ...views.value.filter((view) => view.pinned).map((view) => ({ value: view.id, label: view.name, favorite: true })),
]);
const activeCount = computed(() => Object.values(filters.value).filter((values) => values.length).length);
const activeChips = computed(() =>
  dimensions
    .filter((dimension) => filters.value[dimension.id]?.length)
    .map((dimension) => {
      const values = filters.value[dimension.id] ?? [];
      const labels = values.map((value) => dimension.options.find((option) => option.value === value)?.label ?? value);
      return { id: dimension.id, label: `${dimension.label}: ${labels.join(", ")}` };
    }),
);
const currentSummary = computed(() => {
  const quick = quickItems.value.find((item) => item.value === quickValue.value)?.label ?? "";
  return [quick, ...activeChips.value.map((chip) => chip.label)].filter(Boolean).join(" · ");
});
function removeChip(id: string) {
  filters.value = Object.fromEntries(Object.entries(filters.value).filter(([key]) => key !== id));
}
function clearFilters() {
  filters.value = {};
}
function applyView(id: string) {
  quickValue.value = views.value.find((view) => view.id === id)?.pinned ? id : "all";
}
function saveView(name: string, pinned: boolean) {
  const id = `v${views.value.length + 1}`;
  views.value = [...views.value, { id, name, summary: currentSummary.value, pinned }];
  if (pinned) quickValue.value = id;
}
function togglePin(id: string) {
  views.value = views.value.map((view) => (view.id === id ? { ...view, pinned: !view.pinned } : view));
}
const filtersOpen = ref(false);

const subsection = ref("materials");
const subsections: QuickFilter[] = [
  { value: "materials", label: "Insumos", count: 108 },
  { value: "suppliers", label: "Fornecedores", count: 23 },
  { value: "costs", label: "Custos" },
  { value: "count", label: "Contagem" },
];

// ---- tabela ---------------------------------------------------------------
const density = ref<"comfortable" | "compact">("comfortable");
const orders: Fase2Order[] = [
  { ref: "1048", customer: "Ana Souza", channel: "Site", stage: "Em preparo", total_q: 4870, eta: "10:40", items: ["2 Croissant", "1 Pain au chocolat", "1 Café coado"] },
  { ref: "1049", customer: "Carla Mendes de Albuquerque Ferreira", channel: "iFood", stage: "Atrasado", total_q: 9320, eta: "10:25", items: ["1 Quiche lorraine", "2 Sanduíche de presunto e brie"] },
  { ref: "1050", customer: "Diego Rocha", channel: "Balcão", stage: "Pronto", total_q: 1590, eta: "10:30", items: ["1 Baguete tradicional"] },
  { ref: "1051", customer: "Bruno Lima", channel: "iFood", stage: "Novo", total_q: 6240, eta: "10:55", items: ["4 Madeleine", "1 Chocolate quente"] },
  { ref: "1052", customer: "Elisa Campos", channel: "Site", stage: "Em preparo", total_q: 12880, eta: "11:10", items: ["1 Tarte au citron inteira", "6 Macaron de framboesa"] },
  { ref: "1053", customer: "Fábio Nakamura", channel: "Balcão", stage: "Novo", total_q: 2210, eta: "10:50", items: ["1 Croque-monsieur"] },
  { ref: "1054", customer: "Gabriela Prado", channel: "iFood", stage: "Em preparo", total_q: 5400, eta: "11:00", items: ["2 Pão de campanha"] },
  { ref: "1055", customer: "Heitor Alves", channel: "Site", stage: "Novo", total_q: 3780, eta: "11:20", items: ["1 Brioche", "2 Café coado"] },
];

// ---- registro -------------------------------------------------------------
const recordIndex = ref(2);
const recordOrder = computed(() => orders[recordIndex.value] ?? orders[0]!);

// ---- ação na base -----------------------------------------------------------
const acting = ref(false);
function act() {
  acting.value = true;
  setTimeout(() => {
    acting.value = false;
  }, 1200);
}

// ---- estado de tela -------------------------------------------------------
const states = [
  { key: "loading", title: "Carregando", description: "Buscando os pedidos da fila." },
  { key: "empty", title: "Nada na fila", description: "Nenhum pedido pede você agora." },
  { key: "error", title: "Não deu para carregar a fila", description: "O servidor não respondeu. Tente de novo." },
  { key: "offline", title: "Sem conexão", description: "Sem conexão. O que está na tela é de 10:42." },
] as const;
</script>

<template>
  <div data-operator-catalog="proposal-fase2" data-proposal-page :data-hydrated="hydrated ? 'true' : 'false'">
    <OperatorPage
      title="Proposta: fase 2 da suíte"
      description="As atividades comuns do operador desenhadas com as peças reais do Nuxt UI e o tema do kit. Nada foi mudado nos apps: esta página serve para decidir."
    >
      <!-- Perguntas ao dono -->
      <section id="perguntas" aria-labelledby="perguntas-title" class="space-y-3" data-fase2-section="perguntas">
        <h2 id="perguntas-title" class="text-xl font-semibold">Três perguntas</h2>
        <div class="grid gap-3 lg:grid-cols-3">
          <NuxtCard v-for="question in questions" :key="question.id" :title="question.title">
            <ol class="space-y-2 text-sm">
              <li><span class="font-semibold">1.</span> {{ question.one }}</li>
              <li><span class="font-semibold">2.</span> {{ question.two }}</li>
            </ol>
            <p class="mt-3 text-sm text-muted">
              Recomendo <span class="font-semibold text-default">{{ question.pick }}</span>: {{ question.why }}
            </p>
            <template #footer>
              <NuxtButton label="Ver na página" :to="question.see" color="neutral" variant="ghost" trailing-icon="i-lucide-arrow-down" />
            </template>
          </NuxtCard>
        </div>
      </section>

      <!-- 1. Barras -->
      <Fase2Section
        id="barras"
        title="1. Uma barra, um papel"
        serves="todas as atividades (onde cada coisa mora)"
        :apps="['os oito apps de operador', 'Central']"
      >
        <div class="grid gap-6 xl:grid-cols-[24rem_1fr]">
          <Fase2Frame label="Celular, 390 px" kind="phone" tall>
            <Fase2Band role="Barra superior primária" tone="primary">
              <div class="flex items-center gap-1 px-2 pb-2">
                <NuxtButton icon="i-lucide-menu" color="neutral" variant="ghost" square aria-label="Abrir o menu do app" />
                <p class="min-w-0 flex-1 text-base font-semibold">Pedidos</p>
                <NuxtButton icon="i-lucide-search" color="neutral" variant="ghost" square aria-label="Buscar" />
                <NuxtButton icon="i-lucide-bell" color="neutral" variant="ghost" square aria-label="Avisos" />
                <NuxtButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" square aria-label="Mais ações da fila" />
              </div>
              <p class="px-3 pb-2 text-xs text-muted">Ao vivo · 10:42</p>
            </Fase2Band>
            <Fase2Band role="Barra superior secundária" tone="primary">
              <div class="flex items-center gap-2 px-2 pb-2">
                <Fase2QuickFilters v-model="phoneScope" :items="phoneScopes" label="Recorte rápido da fila" class="min-w-0 flex-1" />
                <NuxtButton icon="i-lucide-sliders-horizontal" label="Filtros (1)" color="neutral" variant="outline" />
              </div>
              <div class="flex gap-2 overflow-x-auto px-2 pb-2">
                <NuxtButton label="Canal: iFood" trailing-icon="i-lucide-x" color="neutral" variant="outline" aria-label="Tirar o recorte Canal: iFood" />
              </div>
            </Fase2Band>
            <Fase2Band role="Aviso da tela">
              <div class="px-2 pb-2">
                <NuxtAlert
                  color="warning"
                  variant="subtle"
                  icon="i-lucide-triangle-alert"
                  title="2 pedidos passaram do horário"
                  description="O 1049 e o 1053 já deveriam ter saído."
                />
              </div>
            </Fase2Band>
            <Fase2Band role="Conteúdo" grow>
              <ul class="space-y-2 px-2 pb-2">
                <li v-for="order in orders.slice(0, 3)" :key="order.ref">
                  <NuxtCard>
                    <div class="flex items-start justify-between gap-2">
                      <div class="min-w-0">
                        <p class="font-semibold tabular-nums">{{ order.ref }}</p>
                        <p class="text-sm text-muted">{{ order.customer }}</p>
                      </div>
                      <NuxtBadge :label="order.stage" :color="order.stage === 'Atrasado' ? 'error' : 'neutral'" />
                    </div>
                  </NuxtCard>
                </li>
              </ul>
            </Fase2Band>
            <Fase2Band role="Ação na base" tone="primary">
              <Fase2ActionBar context-label="Pedido 1048 · Ana Souza" context-value="R$ 48,70" action="Pronto para retirar" />
            </Fase2Band>
            <Fase2Band role="Barra inferior">
              <div class="grid grid-cols-4 px-1 pb-1" aria-label="Maquete da barra inferior">
                <NuxtButton icon="i-lucide-list-checks" label="Pedidos" color="neutral" variant="ghost" active active-color="primary" class="flex-col gap-0.5" />
                <NuxtButton icon="i-lucide-package-check" label="Saída" color="neutral" variant="ghost" class="flex-col gap-0.5" />
                <NuxtButton icon="i-lucide-history" label="Histórico" color="neutral" variant="ghost" class="flex-col gap-0.5" />
                <NuxtButton icon="i-lucide-menu" label="Mais" color="neutral" variant="ghost" class="flex-col gap-0.5" />
              </div>
            </Fase2Band>
          </Fase2Frame>

          <Fase2Frame label="Mesa, 1440 px (rola dentro da moldura em tela estreita)" kind="desk">
            <Fase2Band role="Barra superior primária" tone="primary">
              <div class="flex items-center gap-2 px-3 pb-2">
                <NuxtButton icon="i-lucide-panel-left-close" color="neutral" variant="ghost" square aria-label="Compactar a barra lateral" />
                <p class="text-xl font-semibold">Pedidos</p>
                <NuxtBadge label="Ao vivo" color="success" />
                <div class="flex-1" />
                <NuxtInput icon="i-lucide-search" placeholder="Buscar pedido, cliente, produto ou tela" class="w-88" aria-label="Buscar" />
                <NuxtButton label="Novo pedido" icon="i-lucide-plus" />
                <NuxtButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" square aria-label="Mais ações da fila" />
              </div>
            </Fase2Band>
            <Fase2Band role="Barra superior secundária" tone="primary">
              <div class="flex flex-wrap items-center gap-2 px-3 pb-2">
                <Fase2QuickFilters v-model="deskScope" :items="quickItems" label="Recorte rápido da fila" />
                <div class="flex-1" />
                <NuxtButton label="Hoje, sex 09/10" icon="i-lucide-calendar" color="neutral" variant="outline" />
                <NuxtButton label="Filtros (1)" icon="i-lucide-sliders-horizontal" color="neutral" variant="outline" />
                <NuxtButton label="Favoritos" icon="i-lucide-bookmark" color="neutral" variant="outline" />
                <NuxtButton label="Colunas" icon="i-lucide-columns-3" color="neutral" variant="outline" />
                <span class="text-xs text-muted">18 pedidos · 10:42</span>
              </div>
            </Fase2Band>
            <Fase2Band role="Aviso da tela">
              <div class="px-3 pb-2">
                <NuxtAlert
                  color="warning"
                  variant="subtle"
                  icon="i-lucide-triangle-alert"
                  title="2 pedidos passaram do horário"
                  description="O 1049 e o 1053 já deveriam ter saído."
                />
              </div>
            </Fase2Band>
            <Fase2Band role="Conteúdo" grow>
              <div class="grid grid-cols-3 gap-2 px-3 pb-3">
                <NuxtCard v-for="order in orders.slice(0, 3)" :key="order.ref">
                  <p class="font-semibold tabular-nums">{{ order.ref }}</p>
                  <p class="text-sm text-muted">{{ order.customer }}</p>
                </NuxtCard>
              </div>
            </Fase2Band>
          </Fase2Frame>
        </div>

        <NuxtCard title="Os papéis, faixa a faixa">
          <dl class="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div v-for="row in roles" :key="row.role" class="space-y-1">
              <dt class="font-semibold">{{ row.role }}</dt>
              <dd>Mora: {{ row.has }}.</dd>
              <dd class="text-muted">Nunca: {{ row.never }}.</dd>
            </div>
          </dl>
        </NuxtCard>
      </Fase2Section>

      <!-- 2. Busca -->
      <Fase2Section
        id="busca"
        title="2. Busca em níveis"
        serves="A2 buscar"
        :apps="['os oito apps', 'Central (a busca grande)']"
      >
        <NuxtCard>
          <div class="space-y-3">
            <p class="text-sm">
              Uma busca só, a da suíte. A tela que filtra a própria lista diz isso no campo
              ("Filtrando…"); Tab troca o alcance. Nada de duas buscas visíveis juntas.
            </p>
            <NuxtTabs v-model="searchScope" :items="searchScopes" :content="false" aria-label="Alcance da busca" />
            <NuxtCommandPalette
              :key="searchScope"
              :groups="searchGroups"
              :placeholder="searchPlaceholder"
              class="h-80 rounded-md border border-default"
            />
          </div>
        </NuxtCard>
      </Fase2Section>

      <!-- 3. Filtros -->
      <Fase2Section
        id="filtros"
        title="3. Filtros rápidos, data, filtros completos e favoritos"
        serves="A3 recortar rápido, A4 ir a uma sub-seção, A5 filtrar por completo, A6 escolher o período"
        :apps="['Gestor', 'B.I.', 'PDV', 'Produção', 'Marketing', 'Compras', 'Cozinha']"
      >
        <NuxtCard title="Mesa: a toolbar inteira, funcionando">
          <div class="space-y-3">
            <div class="flex flex-wrap items-center gap-2 border-b border-default pb-3">
              <Fase2QuickFilters v-model="quickValue" :items="quickItems" label="Recorte rápido da fila" class="max-w-full" />
              <div class="flex flex-1 flex-wrap items-center justify-end gap-2">
                <OperatorPeriodPicker v-model="period" :presets="['day', 'week', 'month']" custom label="Período da fila" />
                <FilterBar v-model="filters" :dimensions="dimensions" label="Filtros" />
                <Fase2SavedFilters
                  :views="views"
                  :current-summary="currentSummary"
                  :can-save="Boolean(currentSummary)"
                  @apply="applyView"
                  @save="saveView"
                  @toggle-pin="togglePin"
                />
              </div>
            </div>
            <p class="text-sm text-muted">
              Recorte atual: <span class="text-default">{{ currentSummary || "nenhum" }}</span>. Salve como
              favorito e marque "Mostrar como aba": ele entra no fim do filtro rápido, com a estrela.
            </p>
          </div>
        </NuxtCard>

        <div class="grid gap-6 lg:grid-cols-2">
          <Fase2Frame label="Celular: uma linha, o resto em Filtros (n)" kind="phone">
            <Fase2Band role="Barra superior secundária" tone="primary">
              <div class="flex items-center gap-2 px-2 pb-2">
                <Fase2QuickFilters v-model="quickValue" :items="quickItems" label="Recorte rápido da fila" class="min-w-0 flex-1" />
                <NuxtDrawer v-model:open="filtersOpen" title="Filtros" description="Os recortes desta lista. A lista atrás muda ao aplicar.">
                  <NuxtButton
                    icon="i-lucide-sliders-horizontal"
                    :label="activeCount ? `Filtros (${activeCount})` : 'Filtros'"
                    color="neutral"
                    variant="outline"
                  />
                  <template #body>
                    <div class="space-y-4">
                      <NuxtFormField label="Período">
                        <OperatorPeriodPicker v-model="period" :presets="['day', 'week', 'month']" custom compact label="Período da fila" />
                      </NuxtFormField>
                      <NuxtFormField label="Recortes">
                        <FilterBar v-model="filters" :dimensions="dimensions" label="Filtros" touch />
                      </NuxtFormField>
                      <NuxtFormField label="Favoritos">
                        <Fase2SavedFilters
                          :views="views"
                          :current-summary="currentSummary"
                          :can-save="Boolean(currentSummary)"
                          @apply="applyView"
                          @save="saveView"
                          @toggle-pin="togglePin"
                        />
                      </NuxtFormField>
                    </div>
                  </template>
                  <template #footer>
                    <div class="flex gap-2">
                      <NuxtButton label="Limpar" color="neutral" variant="outline" size="xl" @click="clearFilters" />
                      <NuxtButton label="Ver resultados" size="xl" block @click="filtersOpen = false" />
                    </div>
                  </template>
                </NuxtDrawer>
              </div>
              <div v-if="activeChips.length" class="flex gap-2 overflow-x-auto px-2 pb-2">
                <NuxtButton
                  v-for="chip in activeChips"
                  :key="chip.id"
                  :label="chip.label"
                  trailing-icon="i-lucide-x"
                  color="neutral"
                  variant="outline"
                  :aria-label="`Tirar o recorte ${chip.label}`"
                  @click="removeChip(chip.id)"
                />
              </div>
            </Fase2Band>
            <Fase2Band role="Conteúdo" grow>
              <p class="px-3 pb-3 text-sm text-muted">A lista recortada aparece aqui.</p>
            </Fase2Band>
          </Fase2Frame>

          <NuxtCard title="Sub-seção: a mesma faixa, com rota">
            <div class="space-y-3">
              <p class="text-sm">
                O dono disse: filtro rápido é navegação secundária. A Base do Compras, os Ajustes do
                Marketing e o Sobrou/Lotes do B.I. deixam de ser pílulas dentro dos filtros: viram as
                abas da toolbar esquerda. A diferença é só o destino: a sub-seção muda a URL; o
                recorte muda a busca da URL.
              </p>
              <Fase2QuickFilters v-model="subsection" :items="subsections" label="Seção da Base" />
              <p class="text-sm text-muted">
                Com mais de 4 opções, no celular a faixa vira uma lista de escolha (NuxtSelect), sem
                cortar nenhum nome.
              </p>
            </div>
          </NuxtCard>
        </div>
      </Fase2Section>

      <!-- 4. Tabela -->
      <Fase2Section
        id="tabela"
        title="4. Tabela completa e compacta"
        serves="A7 ler uma lista em tabela e A14 mais ações (o ⋯ da linha)"
        :apps="['Gestor', 'B.I.', 'Compras', 'Marketing', 'Produção', 'PDV']"
      >
        <p class="text-sm">
          Ordene pelo cabeçalho, filtre pelo campo, abra a linha pela seta, esconda colunas, troque a
          densidade. O nome longo do cliente quebra em vez de cortar.
        </p>
        <Fase2Table v-model:density="density" :rows="orders" />
      </Fase2Section>

      <!-- 5. Seleção -->
      <Fase2Section
        id="selecao"
        title="5. Barra de seleção"
        serves="A8 agir em vários de uma vez"
        :apps="['Gestor (fila e Catálogo)', 'Compras (custos e mínimos)', 'Produção (Plano)']"
      >
        <div class="grid gap-6 lg:grid-cols-2">
          <NuxtCard title="Mesa">
            <p class="text-sm">
              Marque duas linhas na tabela acima: a barra de seleção ocupa o lugar da toolbar da tabela
              (pergunta 3, opção 1). Esc ou "Limpar seleção" devolve a toolbar. A lista não pula.
            </p>
          </NuxtCard>
          <Fase2Frame label="Celular: a seleção vira a ação na base" kind="phone">
            <Fase2Band role="Conteúdo" grow>
              <p class="px-3 pb-3 text-sm text-muted">3 pedidos marcados na lista.</p>
            </Fase2Band>
            <Fase2Band role="Ação na base" tone="primary">
              <Fase2ActionBar context-label="Selecionados" context-value="3 pedidos" action="Aceitar 3" secondary="Limpar" />
            </Fase2Band>
          </Fase2Frame>
        </div>
      </Fase2Section>

      <!-- 6. Anterior / próximo -->
      <Fase2Section
        id="registro"
        title="6. Anterior e próximo"
        serves="A9 abrir o registro e ir ao próximo"
        :apps="['Gestor (pedido, cliente)', 'PDV (encomenda)', 'Produção (receita, lote)', 'Compras (item, insumo)', 'Marketing (revisão)']"
      >
        <NuxtCard>
          <div class="space-y-4">
            <div class="flex flex-wrap items-center gap-3">
              <NuxtButton icon="i-lucide-arrow-left" label="Pedidos" color="neutral" variant="ghost" />
              <p class="text-xl font-semibold tabular-nums">Pedido {{ recordOrder.ref }}</p>
              <NuxtBadge :label="recordOrder.stage" />
              <div class="flex-1" />
              <Fase2RecordNav :index="recordIndex" :total="orders.length" noun="Pedido" @go="recordIndex = $event" />
            </div>
            <p class="text-sm">
              {{ recordOrder.customer }} · {{ recordOrder.channel }} · previsto {{ recordOrder.eta }}
            </p>
            <p class="text-sm text-muted">
              "{{ recordIndex + 1 }} de {{ orders.length }}" conta a lista de onde a pessoa veio, com o
              recorte dela. Aberto por link, sem lista de origem, o par não aparece.
            </p>
          </div>
        </NuxtCard>
      </Fase2Section>

      <!-- 7. Ação na base -->
      <Fase2Section
        id="acao"
        title="7. Ação na base no celular"
        serves="A10 fazer a ação do momento"
        :apps="['Gestor', 'Cozinha', 'PDV', 'Compras', 'Marketing', 'B.I.', 'Produção']"
      >
        <p class="text-sm">
          A estrutura de sucesso do Storefront, como regra: o número que a ação mexe, uma ação grande, e
          o motivo escrito quando ela não pode. Fica em fluxo acima da barra inferior (nunca cobre o fim
          da página) e some com o teclado aberto. Na mesa, a ação sobe para a barra superior primária.
        </p>
        <div class="grid gap-6 md:grid-cols-3">
          <Fase2Frame label="Pode agir" kind="phone">
            <Fase2Band role="Conteúdo" grow>
              <p class="px-3 pb-3 text-sm text-muted">Itens e cliente do pedido 1048.</p>
            </Fase2Band>
            <Fase2Band role="Ação na base" tone="primary">
              <Fase2ActionBar
                context-label="Pedido 1048 · Ana Souza"
                context-value="R$ 48,70"
                action="Pronto para retirar"
                :loading="acting"
                @act="act"
              />
            </Fase2Band>
          </Fase2Frame>
          <Fase2Frame label="Não pode, e diz por quê" kind="phone">
            <Fase2Band role="Conteúdo" grow>
              <p class="px-3 pb-3 text-sm text-muted">Itens e cliente do pedido 1049.</p>
            </Fase2Band>
            <Fase2Band role="Ação na base" tone="primary">
              <Fase2ActionBar
                context-label="Pedido 1049 · Pix"
                context-value="R$ 93,20"
                action="Iniciar preparo"
                reason="O Pix ainda não caiu. O pedido libera sozinho quando cair."
              />
            </Fase2Band>
          </Fase2Frame>
          <Fase2Frame label="Recebimento do Compras" kind="phone">
            <Fase2Band role="Conteúdo" grow>
              <p class="px-3 pb-3 text-sm text-muted">Nota 4512 · Moinho Paraná.</p>
            </Fase2Band>
            <Fase2Band role="Ação na base" tone="primary">
              <Fase2ActionBar
                context-label="Conferidos"
                context-value="7 de 9 itens"
                action="Conferir o próximo"
                secondary="Algo não bate"
              />
            </Fase2Band>
          </Fase2Frame>
        </div>
      </Fase2Section>

      <!-- 8. Estado de tela -->
      <Fase2Section
        id="estado"
        title="8. Estado da tela, um só"
        serves="A13 ver o estado da tela"
        :apps="['os oito apps']"
      >
        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <NuxtCard v-for="state in states" :key="state.key">
            <NuxtSkeleton v-if="state.key === 'loading'" class="mb-3 h-16" />
            <NuxtEmpty
              v-if="state.key !== 'loading'"
              :icon="state.key === 'empty' ? 'i-lucide-inbox' : state.key === 'error' ? 'i-lucide-circle-x' : 'i-lucide-wifi-off'"
              :title="state.title"
              :description="state.description"
              :actions="state.key === 'error' ? [{ label: 'Tentar de novo', color: 'neutral', variant: 'outline' }] : undefined"
            />
            <p v-else class="text-sm text-muted">{{ state.description }}</p>
          </NuxtCard>
        </div>
      </Fase2Section>
    </OperatorPage>
  </div>
</template>
