<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

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
const step = ref(1);
const { reveal } = useNextFocus();
watch(step, (value) => {
  void reveal(`catalog-step-${value}`);
});
const notifications = ref(true);
const selection = ref(true);
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
    "UiToolbar",
    "Grupo responsivo de filtros e ações",
    "Ações irmãs no mesmo contexto",
  ],
  [
    "OperatorSplitter",
    "Panes redimensionáveis persistentes",
    "Lista e detalhe no desktop",
  ],
  [
    "UiModal",
    "Decisão bloqueante com foco contido",
    "Confirmação e formulário curto",
  ],
] as const;

onMounted(() => {
  hydrated.value = true;
});
</script>

<template>
  <div
    data-operator-catalog
    data-suite="v4"
    :data-hydrated="hydrated"
    :data-scenario="activeState"
  >
    <OperatorOfficeShell
      v-if="!operationalMode"
      storage-key="operator-kitchen-sink"
    >
      <template #sidebar>
        <NuxtNavigationMenu
          :items="[...kitchenSinkNavigation]"
          orientation="vertical"
          aria-label="Seções do catálogo"
        />
      </template>
      <template #sidebar-header
        ><nav aria-label="Identidade do catálogo">
          <h2 class="op-title">Catálogo do kit</h2>
        </nav></template
      >

      <template #navbar>
        <header
          class="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-3"
        >
          <div class="min-w-0">
            <p class="op-eyebrow text-muted">Operator Kit</p>
            <h1 class="op-heading break-words">Operator Kitchen Sink</h1>
          </div>
          <div class="flex flex-wrap items-center gap-[var(--op-control-gap)]">
            <label class="op-label" for="catalog-state">Cenário</label>
            <NuxtSelect
              id="catalog-state"
              v-model="activeState"
              aria-label="Cenário determinístico"
              :items="[...kitchenSinkStateOptions]"
            />
            <UiButton text="Ação principal" icon="lucide:plus" />
          </div>
        </header>
      </template>

      <template #toolbar>
        <div
          class="overflow-x-auto"
          data-operator-overflow="horizontal"
          role="region"
          aria-label="Atalhos do catálogo"
        >
          <NuxtNavigationMenu
            :items="[...kitchenSinkNavigation]"
            highlight
            aria-label="Atalhos das seções"
          />
        </div>
      </template>

      <main>
        <OperatorPage
          title="Anatomia canônica do operador"
          description="Fixtures herméticas, composição real e um vocabulário visual deliberadamente curto."
        >
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
                  <UiButton text="Primária" /><UiButton
                    text="Secundária"
                    variant="outline"
                  /><UiButton text="Discreta" variant="ghost" />
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
                  Raio único, borda única, três alturas de controle e
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
              title="Regra responsiva"
              description="O splitter existe no desktop. No celular, lista e detalhe viram sequência ou sheet, sem comprimir duas panes."
              color="info"
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
              <NuxtForm :state="{}" class="grid gap-4 md:grid-cols-2">
                <NuxtFormField
                  label="Nome"
                  help="Como aparece para a pessoa operadora"
                  ><NuxtInput placeholder="Nome inequívoco" class="w-full"
                /></NuxtFormField>
                <NuxtFormField label="Responsável"
                  ><NuxtSelect
                    :items="['Ana Ferreira', 'Marcos Lima']"
                    default-value="Ana Ferreira"
                    class="w-full"
                    aria-label="Responsável"
                /></NuxtFormField>
                <NuxtFormField label="Contexto" class="md:col-span-2"
                  ><NuxtTextarea
                    placeholder="Explique necessidade, consequência e próximo passo"
                    class="w-full"
                /></NuxtFormField>
                <UiCheckbox
                  v-model="selection"
                  label="Exige revisão"
                  description="Mantém a decisão explícita antes de concluir."
                />
                <NuxtSwitch
                  v-model="notifications"
                  label="Avisos desta tarefa"
                />
                <div
                  class="flex flex-wrap gap-[var(--op-control-gap)] md:col-span-2"
                  data-action-group
                >
                  <UiButton text="Salvar" /><UiButton
                    text="Cancelar"
                    variant="outline"
                  /><UiButton text="Excluir" variant="destructive" />
                </div>
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
                    Tabela vira cartões quando comparar colunas deixa de caber
                  </h3></template
                >
                <NuxtTable
                  :data="[...kitchenSinkRows]"
                  tabindex="0"
                  aria-label="Pedidos de exemplo"
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
              <UiStepper v-model="step" :items="[...kitchenSinkSteps]" />
              <p
                :data-focus-target="`catalog-step-${step}`"
                class="op-body mt-3"
              >
                Etapa {{ step }}. O foco acompanha a tarefa pelo useNextFocus
                canônico.
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
            <NuxtCard v-if="activeState === 'loading'" aria-label="Carregando">
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
              title="Não foi possível atualizar"
              description="Tente novamente. O dado anterior continua identificado como desatualizado."
              color="error"
            />
            <NuxtAlert
              v-else-if="activeState === 'offline'"
              title="Sem conexão"
              description="Você pode revisar o que já foi carregado. Ações que enviam dados estão indisponíveis."
              color="warning"
            />
            <NuxtAlert
              v-else-if="activeState === 'reconnecting'"
              title="Reconectando"
              description="A tela mantém o último dado confirmado enquanto tenta restabelecer a atualização ao vivo."
              color="info"
            />
            <NuxtAlert
              v-else-if="activeState === 'slow-network'"
              title="A rede está lenta"
              description="A ação continua em andamento. Não repita o gesto enquanto a confirmação não chegar."
              color="warning"
            />
            <NuxtCard v-else-if="activeState === 'readonly'"
              ><h3 class="op-title">Somente leitura</h3>
              <p class="op-body mt-2">
                Os dados estão disponíveis, mas esta pessoa não pode alterar
                esta etapa.
              </p>
              <UiButton class="mt-4" text="Salvar" disabled
            /></NuxtCard>
            <NuxtEmpty
              v-else-if="activeState === 'forbidden'"
              title="Permissão insuficiente"
              description="Peça acesso a uma pessoa administradora. Nenhum dado protegido foi exibido."
              icon="i-lucide-shield-x"
            />
            <NuxtAlert
              v-else-if="activeState === 'success'"
              title="Alteração salva"
              description="O novo estado já é a fonte da verdade e pode ser conferido na lista."
              color="success"
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
              title="Operação ao vivo"
              description="A última leitura útil chegou agora."
              color="success"
            />

            <div class="flex flex-wrap gap-[var(--op-control-gap)]">
              <UiButton text="Abrir confirmação" @click="modalOpen = true" />
              <UiModal
                v-model:open="modalOpen"
                title="Confirmar ação"
                description="A consequência aparece antes do gesto final."
              >
                <template #body
                  ><p class="op-body">
                    O foco fica na camada superior e volta ao acionador quando a
                    camada fecha.
                  </p></template
                >
                <template #footer="{ close }"
                  ><UiButton text="Confirmar" @click="close" /><UiButton
                    text="Voltar"
                    variant="outline"
                    @click="close"
                /></template>
              </UiModal>
              <NuxtPopover>
                <UiButton text="Abrir popover" variant="outline" />
                <template #content
                  ><div class="max-w-64 p-4">
                    <p class="op-body">
                      Informação curta, contextual e não bloqueante.
                    </p>
                  </div></template
                >
              </NuxtPopover>
              <UiButton
                text="Ver shell operacional"
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
      </main>
    </OperatorOfficeShell>

    <section v-else data-operator-audit-id="catalog-operational-shell">
      <OperatorOperationalShell>
        <template #navigation
          ><div
            class="w-[var(--op-rail-compact-width)] bg-rail"
            aria-label="Navegação operacional"
        /></template>
        <template #header>
          <OperatorPageHeader title="Shell operacional">
            <template #subtitle
              ><p class="op-micro mt-1">
                Uma tarefa principal, estado ao vivo e ação persistente
              </p></template
            >
          </OperatorPageHeader>
        </template>
        <div class="p-[var(--op-page-inline-space)]">
          <NuxtCard
            ><p class="op-eyebrow">Tarefa de chão</p>
            <h2 class="op-title">Separar pedido NB-1047</h2>
            <p class="op-body mt-2">
              Chrome estável, conteúdo com largura mínima zero e barra de ação
              própria.
            </p>
            <UiButton
              class="mt-4"
              text="Voltar ao catálogo"
              variant="outline"
              :to="route.path"
          /></NuxtCard>
        </div>
        <template #actions
          ><UiToolbar><UiButton text="Concluir etapa" size="lg" /></UiToolbar
        ></template>
      </OperatorOperationalShell>
    </section>
  </div>
</template>

<style>
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
      [role="tab"]
    ):not([role="separator"]) {
    min-block-size: var(--spacing-control);
    min-inline-size: var(--spacing-control);
  }
}
</style>
