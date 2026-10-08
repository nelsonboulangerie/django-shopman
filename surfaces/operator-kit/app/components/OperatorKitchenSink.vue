<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import {
  kitchenSinkExceptions,
  kitchenSinkMetrics,
  kitchenSinkNavigation,
  kitchenSinkNeeds,
  kitchenSinkQueue,
  kitchenSinkRows,
  kitchenSinkStateOptions,
  kitchenSinkSteps,
  type KitchenSinkState,
} from "../fixtures/operatorKitchenSink";

const route = useRoute();
const router = useRouter();
const hydrated = ref(false);
const modalOpen = ref(false);
const taskDone = ref(false);
const stateAlertOpen = ref(true);
const responsiveAlertOpen = ref(true);
const taskAlertOpen = ref(true);
const searchOpen = ref(false);
const selectedSection = ref("visual-exercises");
const officeShell = ref<{ closeNavigation: () => void } | null>(null);
const { activeHeadings, updateHeadings } = useScrollspy();
watch(activeHeadings, (headings) => {
  const visible = headings
    .flatMap((id) => {
      const section = document.getElementById(id);
      const body = section?.closest<HTMLElement>('[data-slot="body"]');
      return section && body
        ? [
            {
              id,
              distance: Math.abs(
                section.getBoundingClientRect().top -
                  body.getBoundingClientRect().top -
                  12,
              ),
            },
          ]
        : [];
    })
    .sort((a, b) => a.distance - b.distance);
  if (visible[0]) selectedSection.value = visible[0].id;
});
function selectSection(id: string, event?: Event) {
  event?.preventDefault();
  const target = document.getElementById(id);
  const scrollArea = target?.closest<HTMLElement>('[data-slot="body"]');
  if (!target || !scrollArea) return;
  // Rolar apenas o corpo do panel: scrollIntoView também desloca o chrome fixo.
  scrollArea.scrollTo({
    top:
      scrollArea.scrollTop +
      target.getBoundingClientRect().top -
      scrollArea.getBoundingClientRect().top -
      12,
    behavior: "instant",
  });
  target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
  selectedSection.value = id;
  searchOpen.value = false;
  officeShell.value?.closeNavigation();
}
const navigationItems = computed(() =>
  kitchenSinkNavigation.map((item) => ({
    label: item.label,
    "aria-label": "badge" in item ? `${item.label}, ${item.badge} decisões pendentes` : item.label,
    icon: item.icon,
    badge: "badge" in item ? item.badge : undefined,
    active: selectedSection.value === item.to.slice(1),
    onSelect: (event: Event) => selectSection(item.to.slice(1), event),
  })),
);
const searchGroups = computed(() => [
  {
    id: "catalog",
    label: "Seções do catálogo",
    items: kitchenSinkNavigation.map((item) => ({
      label: item.label,
      icon: item.icon,
      onSelect: () => selectSection(item.to.slice(1)),
    })),
  },
]);
const step = ref(0);
const { reveal } = useNextFocus();
watch(step, (value) => {
  void reveal(`catalog-step-${value}`);
});
const notifications = ref(true);
const selection = ref(true);
const formState = reactive({ name: "", owner: "Ana Ferreira", context: "" });
const formSaved = ref(false);
const validateForm = (state: typeof formState) =>
  state.name.trim() ? [] : [{ name: "name", message: "Informe o nome." }];
const operationalMode = computed(() => route.query.mode === "operational");
const activeState = computed<KitchenSinkState>({
  get: () =>
    kitchenSinkStateOptions.some(({ value }) => value === route.query.state)
      ? (route.query.state as KitchenSinkState)
      : "normal",
  set: (state) => {
    const query = { ...route.query };
    if (state === "normal") delete query.state;
    else query.state = state;
    void router.replace({ path: route.path, query });
  },
});
watch(activeState, () => {
  stateAlertOpen.value = true;
});

const splitter = [
  {
    id: "catalog-list",
    slot: "list",
    defaultSize: 62,
    minSize: 35,
    maxSize: 75,
  },
  {
    id: "catalog-detail",
    slot: "detail",
    defaultSize: 38,
    minSize: 25,
    maxSize: 65,
  },
];

const componentLexicon = [
  [
    "OperatorAppRoot",
    "Raiz Nuxt UI, toaster e contexto comum",
    "Uma vez por app",
  ],
  [
    "OperatorOfficeShell",
    "Navegação lateral e conteúdo de escritório",
    "Gestão, análise e cadastros",
  ],
  [
    "OperatorSuiteShell",
    "Rail desktop e barra inferior móvel sobre o Dashboard canônico",
    "App de escritório com seções persistentes",
  ],
  [
    "Título, busca, filtros e ações sobre Navbar e Toolbar oficiais",
    "Cabeçalho principal dentro do shell da suíte",
  ],
  [
    "OperatorOperationalShell",
    "Chrome estável e ação de chão",
    "PDV, Cozinha e Produção",
  ],
  [
    "OperatorPage",
    "Cabeçalho, corpo, links e aside",
    "Página com fluxo de leitura",
  ],
  [
    "OperatorPageHeader",
    "Título, estado e ações da tarefa",
    "Dentro de shell operacional",
  ],
  [
    "NuxtNavigationMenu",
    "Navegação de seções, com filhos e colapso",
    "Sidebar e menus verticais",
  ],
  [
    "NuxtDropdownMenu",
    "Ações secundárias de uma linha ou registro",
    "Menu de contexto sem poluir o card",
  ],
  [
    "OperatorSplitter",
    "Panes redimensionáveis persistentes",
    "Lista e detalhe no desktop",
  ],
] as const;

onMounted(() => {
  hydrated.value = true;
  updateHeadings(
    kitchenSinkNavigation.flatMap((item) => {
      const section = document.getElementById(item.to.slice(1));
      return section ? [section] : [];
    }),
  );
});
</script>

<template>
  <div
    data-operator-catalog
    :data-hydrated="hydrated"
    :data-scenario="activeState"
  >
    <OperatorOfficeShell
      v-if="!operationalMode"
      ref="officeShell"
      storage-key="operator-kitchen-sink"
    >
      <template #sidebar="{ collapsed }">
        <NuxtDashboardSearchButton
          label="Buscar no catálogo"
          :collapsed="collapsed"
        />
        <NuxtNavigationMenu
          :items="navigationItems"
          orientation="vertical"
          :collapsed="collapsed"
          aria-label="Seções do catálogo"
        />
        <NuxtNavigationMenu
          :items="[
            {
              label: 'Referências',
              'aria-label': 'Referências',
              icon: 'i-lucide-book-open',
              children: [
                {
                  label: 'Matriz de necessidades',
                  onSelect: () => selectSection('matrix'),
                },
                {
                  label: 'Exceções justificadas',
                  onSelect: () => selectSection('exceptions'),
                },
              ],
            },
          ]"
          orientation="vertical"
          :collapsed="collapsed"
          aria-label="Referências aninhadas"
          :popover="{ mode: 'click' }"
        />
      </template>
      <template #sidebar-header="{ collapsed }"
        ><div
          class="flex min-w-0 items-center gap-2"
        >
          <NuxtIcon name="i-lucide-flask-conical" class="size-5 shrink-0" />
          <h2 :class="collapsed ? 'sr-only' : 'op-title truncate'">
            Catálogo do kit
          </h2>
        </div></template
      >
      <template #sidebar-footer="{ collapsed }"
        ><NuxtButton
          icon="i-lucide-life-buoy"
          :label="collapsed ? undefined : 'Guia de composição'"
          :square="collapsed"
          class="min-w-0 w-full"
          aria-label="Guia de composição"
          color="neutral"
          variant="ghost"
          @click="selectSection('recipes')"
      /></template>
      <template #search
        ><NuxtDashboardSearch
          v-model:open="searchOpen"
          :groups="searchGroups"
          title="Buscar no catálogo"
          description="Encontre componentes, receitas e referências."
          placeholder="Buscar seção..."
      /></template>

      <template #navbar-actions
        ><NuxtBadge color="neutral" variant="outline"
          >Fixtures locais</NuxtBadge
        ></template
      >

      <template #toolbar>
        <div
          class="flex min-w-0 flex-1 flex-wrap items-center gap-2 py-2"
          data-operator-overflow="horizontal"
          role="region"
          aria-label="Atalhos do catálogo"
        >
          <label class="op-label" for="catalog-state">Cenário</label>
          <NuxtSelect
            id="catalog-state"
            v-model="activeState"
            aria-label="Cenário determinístico"
            :items="[...kitchenSinkStateOptions]"
          />
          <NuxtButton
            label="Shell operacional"
            color="neutral"
            variant="outline"
            :to="{ path: route.path, query: { mode: 'operational' } }"
          />
        </div>
      </template>

      <main>
        <OperatorPage
          title="Anatomia canônica do operador"
          description="Fixtures herméticas, composição real e um vocabulário visual deliberadamente curto."
        >
          <OperatorKitchenSinkDashboard />
          <OperatorKitchenSinkExercises />
          <section
            id="foundations"
            class="space-y-4"
            data-operator-audit-id="catalog-foundations"
          >
            <div>
              <p class="op-eyebrow">Fundamentos</p>
              <h2 class="op-title">Uma escala por responsabilidade</h2>
            </div>
            <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <NuxtCard>
                <p class="op-label">Tipografia</p>
                <p class="op-heading">Heading</p>
                <p class="op-title">Title</p>
                <p class="op-body">Body operacional</p>
                <p class="op-micro">Meta e ajuda</p>
              </NuxtCard>
              <NuxtCard>
                <p class="op-label">Ação</p>
                <div class="mt-3 flex flex-wrap gap-2">
                  <NuxtButton label="Primária" /><NuxtButton
                    label="Secundária"
                    color="neutral"
                    variant="outline"
                  /><NuxtButton label="Discreta" color="neutral" variant="ghost" />
                </div>
                <p class="op-label mt-5">Recorte de fila</p>
                <div class="mt-3 flex flex-wrap gap-2" aria-label="Pills canônicos de filtro">
                  <UiFilterChip active :count="10">
                    <template #icon><Icon name="lucide:check" class="size-4" /></template>
                    Todos
                  </UiFilterChip>
                  <UiFilterChip :count="2">
                    <template #icon><Icon name="lucide:bike" class="size-4" /></template>
                    Entrega
                  </UiFilterChip>
                </div>
              </NuxtCard>
              <NuxtCard>
                <p class="op-label">Estado semântico</p>
                <div class="mt-3 flex flex-wrap gap-2">
                  <NuxtBadge color="success">Sucesso</NuxtBadge
                  ><NuxtBadge color="warning">Atenção</NuxtBadge
                  ><NuxtBadge color="error">Erro</NuxtBadge
                  ><NuxtBadge color="info">Informação</NuxtBadge>
                </div>
              </NuxtCard>
              <NuxtCard>
                <p class="op-label">Geometria</p>
                <p class="op-body mt-3">
                  Raio único, borda única, alvos operacionais de 44 e 48 px e
                  espaçamento por papel sem valores locais.
                </p>
              </NuxtCard>
            </div>
          </section>

          <section
            id="anatomies"
            class="space-y-4"
            data-operator-audit-id="catalog-anatomies"
          >
            <div>
              <p class="op-eyebrow">Anatomias</p>
              <h2 class="op-title">Shell, página, seção, aside e split view</h2>
            </div>
            <div class="hidden md:block">
              <OperatorSplitter
                id="catalog-splitter"
                persistence-key="catalog-demo"
                :items="splitter"
                class="h-80 rounded-md border"
              >
                <template #list>
                  <div
                    class="h-full min-w-0 overflow-auto p-4"
                    data-operator-pane
                    data-pane-min="35"
                  >
                    <h3 class="op-title">Lista</h3>
                    <p class="op-body text-muted">
                      Busca e resultado permanecem no mesmo contexto.
                    </p>
                    <ul class="mt-4 space-y-2">
                      <li
                        v-for="item in kitchenSinkQueue"
                        :key="item.ref"
                        class="rounded-md border p-3"
                      >
                        <p class="op-label">{{ item.ref }}</p>
                        <p class="op-body">{{ item.title }}</p>
                        <p class="op-micro">{{ item.detail }}</p>
                      </li>
                    </ul>
                  </div>
                </template>
                <template #detail>
                  <div
                    class="h-full min-w-0 overflow-auto p-4"
                    data-operator-pane
                    data-pane-min="25"
                  >
                    <p class="op-eyebrow">Detalhe</p>
                    <h3 class="op-title">NB-1047</h3>
                    <dl
                      class="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 op-body"
                    >
                      <dt class="text-muted">Cliente</dt>
                      <dd class="break-words">Ana Ferreira</dd>
                      <dt class="text-muted">Promessa</dt>
                      <dd>Hoje, 15h30</dd>
                      <dt class="text-muted">Próximo ato</dt>
                      <dd>Confirmar a retirada</dd>
                    </dl>
                  </div>
                </template>
              </OperatorSplitter>
            </div>
            <div class="grid gap-3 md:hidden" data-operator-mobile-sequence>
              <NuxtCard>
                <template #header><h3 class="op-title">Fila</h3></template>
                <ul class="space-y-2">
                  <li
                    v-for="item in kitchenSinkQueue"
                    :key="item.ref"
                    class="rounded-md border p-3"
                  >
                    <p class="op-label">{{ item.ref }}</p>
                    <p class="op-body">{{ item.title }}</p>
                    <p class="op-micro">{{ item.detail }}</p>
                  </li>
                </ul>
              </NuxtCard>
              <NuxtCard>
                <template #header
                  ><h3 class="op-title">Detalhe NB-1047</h3></template
                >
                <dl
                  class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 op-body"
                >
                  <dt class="text-muted">Cliente</dt>
                  <dd class="break-words">Ana Ferreira</dd>
                  <dt class="text-muted">Promessa</dt>
                  <dd>Hoje, 15h30</dd>
                  <dt class="text-muted">Próximo ato</dt>
                  <dd>Confirmar a retirada</dd>
                </dl>
              </NuxtCard>
            </div>
            <NuxtAlert
              v-if="responsiveAlertOpen"
              role="status"
              icon="i-lucide-panels-top-left"
              close
              title="Regra responsiva"
              description="O splitter existe no desktop. No celular, lista e detalhe viram sequência ou sheet, sem comprimir duas panes."
              color="info"
              @update:open="responsiveAlertOpen = $event"
            />
          </section>

          <section
            id="components"
            class="space-y-4"
            data-operator-audit-id="catalog-components"
          >
            <div>
              <p class="op-eyebrow">Componentes</p>
              <h2 class="op-title">Léxico, responsabilidade e composição</h2>
            </div>
            <div
              class="overflow-x-auto"
              data-operator-overflow="horizontal"
              tabindex="0"
              aria-label="Léxico de componentes"
            >
              <table
                class="w-full min-w-[44rem] border-separate border-spacing-0 text-left op-body"
              >
                <thead>
                  <tr>
                    <th class="border-b p-3">Nome</th>
                    <th class="border-b p-3">Responsabilidade</th>
                    <th class="border-b p-3">Use quando</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in componentLexicon" :key="row[0]">
                    <th class="border-b p-3 font-medium">{{ row[0] }}</th>
                    <td class="border-b p-3">{{ row[1] }}</td>
                    <td class="border-b p-3">{{ row[2] }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <NuxtCard>
              <template #header
                ><h3 class="op-title">Controles e formulário</h3></template
              >
              <NuxtForm
                :state="formState"
                :validate="validateForm"
                class="grid gap-4 md:grid-cols-2"
                @submit="formSaved = true"
              >
                <NuxtFormField
                  label="Nome"
                  name="name"
                  help="Como aparece para a pessoa operadora"
                  ><NuxtInput
                    v-model="formState.name"
                    placeholder="Nome inequívoco"
                    class="w-full"
                /></NuxtFormField>
                <NuxtFormField label="Responsável" name="owner"
                  ><NuxtSelect
                    v-model="formState.owner"
                    :items="['Ana Ferreira', 'Marcos Lima']"
                    class="w-full"
                    aria-label="Responsável"
                /></NuxtFormField>
                <NuxtFormField
                  label="Contexto"
                  name="context"
                  class="md:col-span-2"
                  ><NuxtTextarea
                    v-model="formState.context"
                    placeholder="Explique necessidade, consequência e próximo passo"
                    class="w-full"
                /></NuxtFormField>
                <NuxtCheckbox
                  v-model="selection"
                  label="Exige revisão"
                  description="Mantém a decisão explícita antes de concluir."
                />
                <NuxtSwitch
                  v-model="notifications"
                  label="Avisos desta tarefa"
                  description="Receba avisos quando esta tarefa mudar de estado."
                  aria-describedby="task-notifications-description"
                  ><template #description
                    ><span id="task-notifications-description"
                      >Receba avisos quando esta tarefa mudar de estado.</span
                    ></template
                  ></NuxtSwitch
                >
                <div
                  class="flex flex-wrap gap-[var(--op-control-gap)] md:col-span-2"
                  data-action-group
                >
                  <NuxtButton label="Salvar formulário" type="submit" />
                  <NuxtButton
                    label="Limpar formulário"
                    color="neutral"
                    variant="outline"
                    @click="
                      formState.name = '';
                      formState.context = '';
                      formSaved = false;
                    "
                  />
                </div>
                <NuxtAlert
                  v-if="formSaved"
                  role="status"
                  class="md:col-span-2"
                  color="success"
                  icon="i-lucide-circle-check"
                  close
                  title="Formulário validado"
                  description="Exemplo salvo apenas nesta fixture local."
                  @update:open="formSaved = $event"
                />
              </NuxtForm>
            </NuxtCard>
          </section>

          <section
            id="recipes"
            class="space-y-4"
            data-operator-audit-id="catalog-recipes"
          >
            <div>
              <p class="op-eyebrow">Receitas</p>
              <h2 class="op-title">
                Dashboard, fila, tabela, detalhe e fluxo em etapas
              </h2>
            </div>
            <div class="grid gap-[var(--op-region-gap)] lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
              <NuxtCard
                as="article"
                variant="outline"
                aria-label="Receita canônica de cartão operacional"
              >
                <template #header>
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <p class="op-heading">H58</p>
                      <p class="op-title">Maria Santos · Loja online</p>
                    </div>
                    <NuxtBadge color="error" variant="soft" label="Bloqueado" />
                  </div>
                </template>
                <div class="flex flex-wrap gap-2">
                  <NuxtBadge color="neutral" variant="soft" icon="i-lucide-store" label="Retirada" />
                  <NuxtBadge color="neutral" variant="soft" icon="i-lucide-package" label="1 item" />
                </div>
                <p class="op-body">1x Croissant</p>
                <NuxtProgress :model-value="0" :max="100" color="primary" size="sm">
                  <template #status>
                    <span class="flex justify-between gap-3 op-micro">
                      <span>CRO · Planejada</span><span class="tabular-nums">0%</span>
                    </span>
                  </template>
                </NuxtProgress>
                <NuxtAlert
                  color="error"
                  variant="soft"
                  icon="i-lucide-lock"
                  title="Expirou às 15:40"
                  description="Gerado às 15:43. Resolva o bloqueio antes de iniciar."
                />
                <div class="flex items-center justify-between gap-3 op-body">
                  <span class="text-muted"><Icon name="lucide:hourglass" class="mr-1 inline size-4" />Pix</span>
                  <strong class="tabular-nums">R$ 13,00</strong>
                </div>
                <template #footer>
                  <NuxtButton
                    block
                    size="xl"
                    color="neutral"
                    variant="outline"
                    icon="i-lucide-lock"
                    label="Iniciar preparo"
                    disabled
                  />
                </template>
              </NuxtCard>
              <NuxtAlert
                color="info"
                variant="subtle"
                icon="i-lucide-book-open-check"
                title="Contrato do cartão operacional"
                description="O card é NuxtCard. Situação e atributos são NuxtBadge. Andamento é NuxtProgress. Impedimento é NuxtAlert. O próximo gesto é NuxtButton. Texto solto serve apenas ao conteúdo, nunca para simular um componente."
              />
            </div>
            <div class="grid gap-[var(--op-region-gap)] md:grid-cols-3">
              <NuxtPageCard
                v-for="metric in kitchenSinkMetrics"
                :key="metric.title"
                :title="metric.title"
                :description="metric.description"
                ><p class="op-figure">{{ metric.value }}</p></NuxtPageCard
              >
            </div>
            <div
              class="grid gap-[var(--op-region-gap)] xl:grid-cols-[minmax(0,1fr)_20rem]"
            >
              <NuxtCard>
                <template #header
                  ><h3 class="op-title">
                    Comparação tabular com rolagem explícita
                  </h3></template
                >
                <NuxtTable
                  :data="[...kitchenSinkRows]"
                  data-operator-overflow="horizontal"
                  tabindex="0"
                  caption="Pedidos de exemplo"
                />
              </NuxtCard>
              <NuxtPageAside
                ><p class="op-label">Aside</p>
                <p class="op-body mt-2">
                  Explica a decisão sem competir com o formulário ou a ação
                  principal.
                </p></NuxtPageAside
              >
            </div>
            <NuxtCard>
              <template #header
                ><h3 class="op-title">Fluxo em etapas</h3></template
              >
              <NuxtStepper
                v-model="step"
                :items="[...kitchenSinkSteps]"
                :linear="false"
                class="w-full"
              />
              <p
                :data-focus-target="`catalog-step-${step}`"
                class="op-body mt-3"
              >
                Etapa {{ step + 1 }}. O foco acompanha a tarefa pelo
                useNextFocus canônico.
              </p>
            </NuxtCard>
          </section>

          <section
            id="states"
            class="space-y-4"
            data-operator-audit-id="catalog-states"
          >
            <div>
              <p class="op-eyebrow">Estados</p>
              <h2 class="op-title">
                O cenário selecionado é endereçável e não usa dados vivos
              </h2>
            </div>
            <NuxtCard v-if="activeState === 'loading'" aria-busy="true" role="status" aria-label="Carregando dados do catálogo">
              <div class="space-y-3">
                <NuxtSkeleton class="h-6 w-2/3" /><NuxtSkeleton
                  class="h-11 w-full"
                /><NuxtSkeleton class="h-24 w-full" />
              </div>
            </NuxtCard>
            <NuxtEmpty
              v-else-if="activeState === 'empty'"
              title="Nenhum item encontrado"
              description="Ajuste os filtros ou crie o primeiro item."
              icon="i-lucide-inbox"
            />
            <NuxtAlert
              v-else-if="activeState === 'error'"
              v-show="stateAlertOpen"
              role="alert"
              icon="i-lucide-circle-alert"
              close
              title="Não foi possível atualizar"
              description="Tente novamente. O dado anterior continua identificado como desatualizado."
              color="error"
              @update:open="stateAlertOpen = $event"
            />
            <NuxtAlert
              v-else-if="activeState === 'offline'"
              v-show="stateAlertOpen"
              role="status"
              icon="i-lucide-wifi-off"
              close
              title="Sem conexão"
              description="Você pode revisar o que já foi carregado. Ações que enviam dados estão indisponíveis."
              color="warning"
              @update:open="stateAlertOpen = $event"
            />
            <NuxtAlert
              v-else-if="activeState === 'reconnecting'"
              v-show="stateAlertOpen"
              role="status"
              icon="i-lucide-refresh-cw"
              close
              title="Reconectando"
              description="A tela mantém o último dado confirmado enquanto tenta restabelecer a atualização ao vivo."
              color="info"
              @update:open="stateAlertOpen = $event"
            />
            <NuxtAlert
              v-else-if="activeState === 'slow-network'"
              v-show="stateAlertOpen"
              role="status"
              icon="i-lucide-clock"
              close
              title="A rede está lenta"
              description="A ação continua em andamento. Não repita o gesto enquanto a confirmação não chegar."
              color="warning"
              @update:open="stateAlertOpen = $event"
            />
            <NuxtCard v-else-if="activeState === 'readonly'"
              ><h3 class="op-title">Somente leitura</h3>
              <p class="op-body mt-2">
                Os dados estão disponíveis, mas esta pessoa não pode alterar
                esta etapa.
              </p>
              <NuxtFormField class="mt-3" label="Nome confirmado"
                ><NuxtInput model-value="Ana Ferreira" readonly class="w-full"
              /></NuxtFormField>
              <NuxtButton class="mt-4" label="Salvar" disabled
            /></NuxtCard>
            <NuxtEmpty
              v-else-if="activeState === 'forbidden'"
              title="Permissão insuficiente"
              description="Peça acesso a uma pessoa administradora. Nenhum dado protegido foi exibido."
              icon="i-lucide-shield-x"
            />
            <NuxtAlert
              v-else-if="activeState === 'success'"
              v-show="stateAlertOpen"
              role="status"
              icon="i-lucide-circle-check"
              close
              title="Alteração salva"
              description="O novo estado já é a fonte da verdade e pode ser conferido na lista."
              color="success"
              @update:open="stateAlertOpen = $event"
            />
            <NuxtCard v-else-if="activeState === 'extreme-content'"
              ><h3 class="op-title break-words [overflow-wrap:anywhere]">
                CONTEUDO-SEM-SEPARADOR-QUE-NUNCA-DEVE-FORCAR-SCROLL-HORIZONTAL-OU-DIMINUIR-A-TIPOGRAFIA
              </h3>
              <p class="op-body mt-2 break-words">
                R$ 999.999.999,99, 9.999 unidades e uma observação longa
                permanecem legíveis em 320 px e a 200% de zoom.
              </p></NuxtCard
            >
            <NuxtAlert
              v-else
              v-show="stateAlertOpen"
              role="status"
              icon="i-lucide-activity"
              close
              title="Operação ao vivo"
              description="A última leitura útil chegou agora."
              color="success"
              @update:open="stateAlertOpen = $event"
            />

            <div class="flex flex-wrap gap-[var(--op-control-gap)]">
              <NuxtModal
                v-model:open="modalOpen"
                title="Confirmar ação"
                description="A consequência aparece antes do gesto final."
              >
                <NuxtButton label="Abrir confirmação" />
                <template #body
                  ><p class="op-body">
                    O foco fica na camada superior e volta ao acionador quando a
                    camada fecha.
                  </p></template
                >
                <template #footer="{ close }"
                  ><NuxtButton label="Confirmar" @click="close" /><NuxtButton
                    label="Voltar"
                    color="neutral"
                    variant="outline"
                    @click="close"
                /></template>
              </NuxtModal>
              <NuxtPopover>
                <NuxtButton label="Abrir popover" color="neutral" variant="outline" />
                <template #content
                  ><div class="max-w-64 p-4">
                    <p class="op-body">
                      Informação curta, contextual e não bloqueante.
                    </p>
                  </div></template
                >
              </NuxtPopover>
              <NuxtSlideover
                title="Detalhe do pedido"
                description="Inspeção contextual sem sair da lista."
              >
                <NuxtButton
                  label="Abrir detalhe lateral"
                  color="neutral"
                  variant="outline"
                />
                <template #body
                  ><NuxtFormField label="Observação do pedido"
                    ><NuxtTextarea
                      v-model="formState.context"
                      class="w-full" /></NuxtFormField
                ></template>
                <template #footer="{ close }"
                  ><NuxtButton label="Concluir inspeção" @click="close"
                /></template>
              </NuxtSlideover>
              <NuxtButton
                label="Ver shell operacional"
                color="neutral"
                variant="outline"
                :to="{ path: route.path, query: { mode: 'operational' } }"
              />
            </div>
          </section>

          <section
            id="matrix"
            class="space-y-4"
            data-operator-audit-id="catalog-matrix"
          >
            <div>
              <p class="op-eyebrow">Matriz rastreável</p>
              <h2 class="op-title">Necessidade real antes de variante</h2>
            </div>
            <div
              class="overflow-x-auto"
              data-operator-overflow="horizontal"
              tabindex="0"
              aria-label="Matriz de necessidades"
            >
              <table
                class="w-full min-w-[48rem] border-separate border-spacing-0 text-left op-body"
              >
                <thead>
                  <tr>
                    <th class="border-b p-3">Apps</th>
                    <th class="border-b p-3">Necessidade</th>
                    <th class="border-b p-3">Solução canônica</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in kitchenSinkNeeds"
                    :key="`${row.apps}-${row.need}`"
                  >
                    <td class="border-b p-3">{{ row.apps }}</td>
                    <td class="border-b p-3">{{ row.need }}</td>
                    <td class="border-b p-3">{{ row.solution }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section
            id="exceptions"
            class="space-y-4"
            data-operator-audit-id="catalog-exceptions"
          >
            <div>
              <p class="op-eyebrow">Exceções</p>
              <h2 class="op-title">
                Comportamento específico não autoriza linguagem visual paralela
              </h2>
            </div>
            <div class="grid gap-3 md:grid-cols-2">
              <NuxtCard
                v-for="item in kitchenSinkExceptions"
                :key="`${item.app}-${item.useCase}`"
              >
                <p class="op-label">{{ item.app }}</p>
                <h3 class="op-title mt-1">{{ item.useCase }}</h3>
                <p class="op-body mt-2 text-muted">{{ item.limitation }}</p>
              </NuxtCard>
            </div>
          </section>
        </OperatorPage>
        <footer
          class="border-t border-default px-[var(--op-page-inline-space)] py-4"
        >
          <nav
            aria-label="Rodapé do catálogo"
            class="flex flex-wrap items-center gap-3"
          >
            <NuxtButton
              v-for="item in kitchenSinkNavigation.slice(-3)"
              :key="item.to"
              color="neutral"
              variant="link"
              @click="selectSection(item.to.slice(1))"
              >{{ item.label }}</NuxtButton
            >
            <span class="op-micro"
              >Busca <NuxtKbd value="meta" /> <NuxtKbd value="k" />. Fechar
              <NuxtKbd value="escape" />.</span
            >
          </nav>
        </footer>
      </main>
    </OperatorOfficeShell>

    <div v-else data-operator-audit-id="catalog-operational-shell">
      <OperatorOperationalShell>
        <template #navigation
          ><NuxtNavigationMenu
            :items="[
              {
                label: 'Catálogo',
                icon: 'i-lucide-flask-conical',
                to: route.path,
              },
              {
                label: 'Tarefa de chão',
                icon: 'i-lucide-chef-hat',
                active: true,
              },
            ]"
            orientation="vertical"
            aria-label="Navegação operacional"
        /></template>
        <template #header>
          <NuxtDashboardNavbar as="header" title="Shell operacional" />
        </template>
        <div>
          <NuxtCard
            ><p class="op-eyebrow">Tarefa de chão</p>
            <h2 class="op-title">Separar pedido NB-1047</h2>
            <p class="op-body mt-2">
              Chrome estável, conteúdo com largura mínima zero e barra de ação
              própria.
            </p>
            <NuxtButton
              class="mt-4"
              label="Voltar ao catálogo"
              color="neutral"
              variant="outline"
              :to="route.path"
          /></NuxtCard>
          <NuxtAlert
            v-if="taskDone && taskAlertOpen"
            role="status"
            class="mt-4"
            title="Etapa concluída"
            description="Estado confirmado pela fixture local."
            color="success"
            icon="i-lucide-circle-check"
            close
            @update:open="taskAlertOpen = $event"
          />
        </div>
        <template #actions
          ><NuxtButton
            label="Concluir etapa"
            size="lg"
            :disabled="taskDone"
            @click="taskDone = true"
          />
          ></template
        >
      </OperatorOperationalShell>
    </div>
  </div>
</template>

<style>
/* O catálogo mostra cada peça como ela é tocada no balcão: com ponteiro touch, todo
   controle do catálogo ganha o envelope operacional de 44/48 px que a varredura de
   geometria do Kitchen Sink exige. Estava no `main` e saiu no snapshot WIP do Gestor
   (7e6bb83de) sem decisão escrita; volta até a decisão de alvo de toque ser tomada
   para os nove apps (WP-OPERADOR-NUXTUI-ONDAS, onda 0). */
@media (pointer: coarse) {
  [data-operator-catalog]
    :where(
      button,
      a[href],
      input:not([type="hidden"]),
      select,
      textarea,
      [role="button"],
      [role="link"],
      [role="tab"],
      /* Segmentos de data/hora (reka) são divs `spinbutton` de ~20 px de altura;
         no toque eles precisam do mesmo envelope de 44/48 px dos outros controles. */
      [role="spinbutton"]
    ):not([role="separator"]):not([role="checkbox"]):not([role="radio"]):not(
      [role="switch"]
    ) {
    min-block-size: var(--spacing-control);
    min-inline-size: var(--spacing-control);
  }
}
</style>
