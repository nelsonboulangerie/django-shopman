<script setup lang="ts">
// Proposta visual da fase 2, RODADA 2 (docs/plans/WP-FASE2-UX-OPERADOR.md, seções 10 e
// 11). A rodada 1 mostrou as peças uma a uma; o dono respondeu as três perguntas, fez
// observações peça a peça e pediu para estressar as peças JUNTAS. Esta página mostra o
// que mudou em cada peça e leva às quatro telas compostas (`/proposal/fase2/<tela>`),
// onde elas disputam espaço e atenção. Nada aqui é contrato; o que for aprovado nasce no
// `operator-kit` (PRs K0 a K8) e esta página morre junto.
//
// A página NÃO veste o marcador do catálogo (`data-operator-catalog`): ele sobe campo e
// lista para 44 px, e a observação do dono é justamente a altura de campo igual à do
// botão. Aqui os dois têm a altura `md` do Nuxt UI.
import { useLocalStorage } from "@vueuse/core";
import { computed, onMounted, ref } from "vue";

import { HISTORY, ORDER_DIMENSIONS, ORDER_GROUPS, ORDER_QUICK, ORDER_TEXT_FIELDS, ORDER_VIEWS, PERIODS, QUEUE } from "../../../data/fase2";
import type { Fase2FilterConfig } from "../../../data/fase2Filters";
import { applyView, facetsOf, removeFacet } from "../../../data/fase2Filters";
import type { Fase2FilterState, SavedView } from "../../../types/fase2";

useHead({ title: "Proposta: fase 2 da suíte" });

const hydrated = ref(false);
onMounted(() => {
  hydrated.value = true;
});

const decided = [
  { q: "Densidade da tabela", a: "Compacta é o padrão; Confortável fica como alternância, guardada por dispositivo. A linha aberta não compacta." },
  { q: "Favoritos de filtro", a: "Cada pessoa tem os seus, e o gerente publica para a equipe. Nasce pelos pessoais; o publicar está desenhado no diálogo de salvar." },
  { q: "Barra de seleção na mesa", a: "Ocupa o lugar da toolbar enquanto houver marcados." },
];

const screens = [
  {
    to: "/proposal/fase2/fila",
    title: "Fila do Gestor",
    stresses: "Celular: selo ao vivo, busca, Avisos e ⋯ na barra do topo; filtros com 2 recortes; 3 pedidos marcados; ação flutuante; barra inferior; aviso urgente. Mesa: a mesma fila em colunas, com a barra de seleção no lugar da toolbar.",
    states: [
      { label: "Tudo junto", query: "" },
      { label: "Sem seleção", query: "livre" },
      { label: "Filtros abertos", query: "filtros" },
      { label: "Busca aberta", query: "busca" },
      { label: "Vazia", query: "vazio" },
      { label: "Com erro", query: "erro" },
    ],
  },
  {
    to: "/proposal/fase2/historico",
    title: "Histórico do Gestor",
    stresses: "Mesa: tabela compacta, uma linha aberta, 3 marcados, um favorito aplicado e o detalhe ao lado com anterior e próximo. Celular: as colunas que cabem, o detalhe em tela cheia.",
    states: [
      { label: "Tudo junto", query: "" },
      { label: "Só a seleção", query: "selecao" },
      { label: "Só o detalhe", query: "detalhe" },
      { label: "Sem recorte", query: "livre" },
      { label: "Filtros abertos", query: "filtros" },
    ],
  },
  {
    to: "/proposal/fase2/compras",
    title: "Base do Compras",
    stresses: "Celular: sub-seções e filtros na mesma linha, a lista longa agrupada por fornecedor, o cabeçalho do grupo grudado, o aviso e a dica de que há mais abaixo.",
    states: [
      { label: "Agrupada", query: "" },
      { label: "Sem agrupar", query: "livre" },
      { label: "Filtros abertos", query: "filtros" },
    ],
  },
  {
    to: "/proposal/fase2/pdv",
    title: "Balcão do PDV",
    stresses: "A carta branca: a barra da venda no lugar da toolbar, o campo de produto sempre à vista, a comanda fixa na mesa e flutuante no celular.",
    states: [
      { label: "Venda aberta", query: "" },
      { label: "Comanda aberta", query: "comanda" },
      { label: "Comanda vazia", query: "vazio" },
    ],
  },
];

const changes = [
  { said: "No celular, \"Ao vivo · 10:42\" é um selo.", did: "Selo ao lado do título; sem espaço, desce para a linha de baixo antes de espremer o título. Muda de cor quando o vivo cai." },
  { said: "Botão de filtro só com ícone, com o número de recortes.", did: "No celular, só o ícone, com o número no canto (o chip numerado do tema). Na mesa, ícone, \"Filtros\" e o mesmo número." },
  { said: "Busca em níveis no canônico.", did: "NuxtDashboardSearch e NuxtDashboardSearchButton oficiais. Os níveis viraram os grupos da paleta, em ordem fixa: Nesta tela, Neste app, Na suíte. Sem abas próprias." },
  { said: "Filtro repensado e igual no celular e na mesa, favoritos primeiro (Odoo).", did: "Um painel só, sobre NuxtCommandPalette: Favoritos, Filtros rápidos, Data, Agrupar por, Filtros completos e, no pé, Salvar como favorito. Drawer de baixo no celular, Popover na mesa." },
  { said: "Tabela compacta por padrão; a linha aberta não compacta.", did: "Compacta é o padrão; Confortável mora no botão Exibir (com as colunas), guardada no dispositivo. O conteúdo aberto ganha o respiro da confortável." },
  { said: "Campo de busca da tabela menor e com padding.", did: "O campo foi para a toolbar da tela (13 rem, com folga), e a tabela entra no cartão sem barra própria." },
  { said: "Barra de seleção no lugar da barra de filtros.", did: "Na mesa, ela troca a toolbar e diz em que recorte a seleção foi feita. No celular, ela é a ação flutuante." },
  { said: "Copy de estado.", did: "\"Nenhum pedido precisa de você agora.\" e \"Não foi possível carregar a fila\", e o mesmo tom nos outros estados." },
  { said: "Ação na base com mais contraste, flutuante, escura.", did: "Flutua 12 px acima da barra inferior, em superfície invertida (escura no tema claro), com o botão claro: a estrutura do Storefront." },
  { said: "Cartões sem destaque de cabeçalho e rodapé.", did: "O cartão de pedido é um bloco só, com respiro de 12 px. Cabeçalho e rodapé só onde separam algo de fato." },
  { said: "Altura de campo igual à de botão.", did: "Campo, lista de escolha e botão na altura md (32 px na mesa). O degrau xl (48 px) fica para o toque crítico, nos dois ao mesmo tempo." },
];

// ---- peças vivas --------------------------------------------------------------
const config: Fase2FilterConfig = {
  noun: "pedidos",
  quick: ORDER_QUICK,
  periods: PERIODS,
  defaultPeriod: "today",
  groups: ORDER_GROUPS,
  dimensions: ORDER_DIMENSIONS,
  textFields: ORDER_TEXT_FIELDS,
};
const views = ref<SavedView[]>(ORDER_VIEWS.map((view) => ({ ...view })));
const filters = ref<Fase2FilterState>(applyView(ORDER_VIEWS[1]!, "today"));
const facets = computed(() => facetsOf(filters.value, config, views.value));

const density = useLocalStorage<"compact" | "comfortable">("fase2-table-density", "compact", { initOnMounted: true });
const visibility = ref<Record<string, boolean>>({});
const tableFilter = ref("");
const selection = ref<Record<string, boolean>>({});
const expanded = ref<Record<string, boolean>>({ "1044": true });
const selectedCount = computed(() => Object.values(selection.value).filter(Boolean).length);
const viewColumns = [
  { id: "date", label: "Dia" },
  { id: "customer", label: "Cliente" },
  { id: "channel", label: "Canal" },
  { id: "payment", label: "Pagamento" },
  { id: "stage", label: "Situação" },
];

const selo = [
  { label: "Ao vivo · 10:42", color: "success" as const },
  { label: "Reconectando · 10:42", color: "warning" as const },
  { label: "Sem conexão desde 10:42", color: "error" as const },
];
const pick = ref("ifood");
</script>

<template>
  <div data-proposal="fase2" data-proposal-page :data-hydrated="hydrated ? 'true' : 'false'">
    <OperatorPage
      title="Proposta: fase 2 da suíte, rodada 2"
      description="As observações do dono aplicadas peça a peça, e as peças juntas em quatro telas compostas, no celular e na mesa. Nada foi mudado nos apps: esta página serve para decidir."
    >
      <section aria-labelledby="decidido-title" class="space-y-3" data-fase2-section="decidido">
        <h2 id="decidido-title" class="text-xl font-semibold">Decidido na rodada 1</h2>
        <dl class="grid gap-3 text-sm lg:grid-cols-3">
          <div v-for="item in decided" :key="item.q" class="space-y-1">
            <dt class="font-semibold">{{ item.q }}</dt>
            <dd class="text-muted">{{ item.a }}</dd>
          </div>
        </dl>
      </section>

      <section id="telas" aria-labelledby="telas-title" class="space-y-3" data-fase2-section="telas">
        <h2 id="telas-title" class="text-xl font-semibold">As peças juntas: quatro telas</h2>
        <p class="text-sm text-muted">
          Cada tela abre em tela cheia. A mesma rota é o celular (abaixo de 640 px) e a mesa: o arranjo muda por CSS, como a régua única pede.
        </p>
        <div class="grid gap-3 lg:grid-cols-2">
          <NuxtCard v-for="screen in screens" :key="screen.to" :ui="{ body: 'p-3 sm:p-3 space-y-2' }">
            <h3 class="font-semibold text-highlighted">{{ screen.title }}</h3>
            <p class="text-sm text-muted">{{ screen.stresses }}</p>
            <div class="flex flex-wrap gap-2">
              <NuxtButton
                v-for="state in screen.states"
                :key="state.label"
                :label="state.label"
                :to="state.query ? `${screen.to}?estado=${state.query}` : screen.to"
                color="neutral"
                variant="outline"
                trailing-icon="i-lucide-arrow-up-right"
              />
            </div>
          </NuxtCard>
        </div>
      </section>

      <section id="mudancas" aria-labelledby="mudancas-title" class="space-y-3" data-fase2-section="mudancas">
        <h2 id="mudancas-title" class="text-xl font-semibold">O que mudou, observação por observação</h2>
        <ol class="divide-y divide-default text-sm">
          <li v-for="(change, index) in changes" :key="change.said" class="grid gap-1 py-2 sm:grid-cols-[2rem_1fr_1.4fr] sm:gap-3">
            <span class="tabular-nums text-muted">{{ index + 1 }}.</span>
            <span class="font-medium text-highlighted">{{ change.said }}</span>
            <span class="text-default">{{ change.did }}</span>
          </li>
        </ol>
      </section>

      <section id="pecas" aria-labelledby="pecas-title" class="space-y-6" data-fase2-section="pecas">
        <h2 id="pecas-title" class="text-xl font-semibold">As peças revisadas, vivas</h2>

        <div class="space-y-2">
          <h3 class="font-semibold">Selo, busca e filtros na mesma linha</h3>
          <div class="flex flex-wrap items-center gap-2">
            <NuxtBadge v-for="item in selo" :key="item.label" :label="item.label" :color="item.color" icon="i-lucide-radio" />
          </div>
          <div class="flex flex-wrap items-center gap-2 rounded-md border border-default bg-card p-2">
            <Fase2Search
              screen="a fila"
              :screen-items="QUEUE.slice(0, 2).map((o) => ({ label: `${o.ref} · ${o.customer}`, suffix: o.stage, icon: 'i-lucide-receipt' }))"
              app="Gestor"
              :app-items="[{ label: 'Ana Souza', suffix: 'Clientes', icon: 'i-lucide-user' }]"
              :suite-items="[{ label: 'Croissant', suffix: 'Catálogo', icon: 'i-lucide-croissant' }]"
            />
            <Fase2Facets :facets="facets" @remove="(id) => (filters = removeFacet(filters, id, 'today'))" />
            <span class="ms-auto" />
            <Fase2Filters v-model="filters" v-model:views="views" :config="config" :result-count="7" />
          </div>
        </div>

        <div class="space-y-2">
          <h3 class="font-semibold">Altura harmonizada: campo, lista e botão</h3>
          <div class="flex flex-wrap items-center gap-2" data-fase2-heights>
            <NuxtInput placeholder="Filtrar estes pedidos" icon="i-lucide-search" class="w-52" aria-label="Exemplo de campo" />
            <NuxtSelect
              v-model="pick"
              :items="[{ label: 'iFood', value: 'ifood' }, { label: 'Site', value: 'site' }]"
              class="w-32"
              aria-label="Exemplo de lista de escolha"
            />
            <NuxtButton label="Filtros" icon="i-lucide-sliders-horizontal" color="neutral" variant="outline" />
            <NuxtButton label="Aceitar" />
          </div>
        </div>

        <div class="space-y-2">
          <h3 class="font-semibold">Tabela compacta (marque linhas: a seleção troca a toolbar)</h3>
          <NuxtCard :ui="{ body: 'p-0 sm:p-0' }">
            <div class="border-b border-default">
              <div v-if="selectedCount" class="flex min-h-12 items-center gap-2 px-3 py-1.5">
                <span class="text-sm font-semibold" aria-live="polite">{{ selectedCount }} selecionados</span>
                <NuxtButton label="Limpar seleção" color="neutral" variant="ghost" @click="selection = {}" />
                <NuxtButton :label="`Exportar ${selectedCount}`" icon="i-lucide-download" class="ms-auto" />
              </div>
              <div v-else class="flex min-h-12 items-center gap-2 px-3 py-1.5">
                <NuxtInput v-model="tableFilter" icon="i-lucide-search" placeholder="Filtrar estes pedidos" aria-label="Filtrar os pedidos da tabela" class="w-52" />
                <span class="ms-auto" />
                <Fase2TableView v-model:density="density" v-model:visibility="visibility" :columns="viewColumns" />
              </div>
            </div>
            <Fase2Table
              v-model:global-filter="tableFilter"
              v-model:row-selection="selection"
              v-model:expanded="expanded"
              v-model:column-visibility="visibility"
              :rows="HISTORY.slice(0, 6)"
              :density="density"
              caption="Pedidos (exemplo)"
            />
          </NuxtCard>
        </div>

        <div class="grid gap-6 lg:grid-cols-2">
          <div class="space-y-2">
            <h3 class="font-semibold">Ação flutuante</h3>
            <div class="rounded-md border border-dashed border-default bg-default p-3">
              <Fase2ActionBar context-label="Pedido 1048 · Ana Souza" context-value="R$ 48,70" action="Pronto para retirar" icon="i-lucide-check" />
            </div>
            <div class="rounded-md border border-dashed border-default bg-default p-3">
              <Fase2ActionBar
                context-label="Pedido 1049 · Pix"
                context-value="R$ 93,20"
                action="Iniciar preparo"
                reason="O Pix ainda não caiu. O pedido libera sozinho quando cair."
              />
            </div>
          </div>
          <div class="space-y-2">
            <h3 class="font-semibold">Cartão sem cabeçalho nem rodapé</h3>
            <div class="grid gap-2">
              <Fase2OrderCard :order="QUEUE[0]!" />
              <Fase2OrderCard :order="QUEUE[1]!" :selected="true" />
            </div>
          </div>
        </div>

        <div class="space-y-2">
          <h3 class="font-semibold">Estados da tela, na voz escolhida</h3>
          <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Fase2ScreenState kind="empty" noun="a fila" />
            <Fase2ScreenState kind="error" noun="a fila" />
            <Fase2ScreenState kind="offline" noun="a fila" />
            <Fase2ScreenState kind="no-results" noun="a fila" />
          </div>
        </div>
      </section>

      <section id="precedencia" aria-labelledby="precedencia-title" class="space-y-2" data-fase2-section="precedencia">
        <h2 id="precedencia-title" class="text-xl font-semibold">Regras de precedência</h2>
        <p class="text-sm text-muted">
          O que as quatro telas revelaram, por escrito, em docs/plans/WP-FASE2-UX-OPERADOR.md, seção 11: quem cede, quem some, quem vai para o ⋯ ou para o painel, e o que nunca fica coberto.
        </p>
      </section>
    </OperatorPage>
  </div>
</template>
