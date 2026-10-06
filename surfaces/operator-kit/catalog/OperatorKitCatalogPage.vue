<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

const nav = [
  { label: "Painel", icon: "i-lucide-layout-dashboard", to: "#dashboard" },
  { label: "Formulário", icon: "i-lucide-clipboard-pen", to: "#form" },
  { label: "Tabela", icon: "i-lucide-table", to: "#table" },
  { label: "Estados", icon: "i-lucide-circle-alert", to: "#states" },
];
const tabs = [
  { label: "Visão", slot: "overview" },
  { label: "Atividade", slot: "activity" },
];
const rows = [
  { pedido: "NB-1042", cliente: "Ana Ferreira", estado: "Pronto", total: "R$ 148,90" },
  { pedido: "NB-1043", cliente: "Nome extremo que prova a segunda linha deliberada", estado: "Em preparo", total: "R$ 9.999,99" },
];
const modalOpen = ref(false);
const sidebarOpen = ref(false);
const hydrated = ref(false);
const route = useRoute();
const operationalMode = computed(() => route.query.mode === "operational");
const splitter = [
  { id: "catalog-list", slot: "list", defaultSize: 62, minSize: 35, maxSize: 75 },
  { id: "catalog-detail", slot: "detail", defaultSize: 38, minSize: 25, maxSize: 65 },
];
onMounted(() => { hydrated.value = true; });
</script>

<template>
  <OperatorAppRoot>
    <div data-operator-catalog data-suite="v3" :data-hydrated="hydrated">
      <OperatorOfficeShell v-if="!operationalMode" storage-key="operator-kit-catalog">
        <template #sidebar>
          <NuxtSidebar v-model:open="sidebarOpen" title="Catálogo do kit" collapsible="offcanvas" close rail>
            <NuxtNavigationMenu :items="nav" orientation="vertical" />
          </NuxtSidebar>
        </template>
        <template #navbar>
          <div class="flex min-w-0 flex-1 items-center justify-between gap-3">
            <div><p class="op-eyebrow text-muted">Operator Kit</p><h1 class="op-heading">Catálogo canônico</h1></div>
            <UiButton text="Nova ação" icon="lucide:plus" />
          </div>
        </template>
        <template #toolbar>
          <div class="overflow-x-auto" data-operator-overflow="horizontal">
            <NuxtNavigationMenu :items="nav" highlight />
          </div>
        </template>

        <OperatorPage title="Anatomias compartilhadas" description="Layouts e componentes oficiais com identidade Shopman.">
          <section id="dashboard" class="space-y-4" data-operator-audit-id="catalog-dashboard">
            <h2 class="op-title">Dashboard e cards</h2>
            <div class="grid gap-[var(--op-region-gap)] md:grid-cols-3">
              <NuxtPageCard title="Pedidos abertos" description="12 aguardam uma decisão"><p class="op-figure">24</p></NuxtPageCard>
              <NuxtPageCard title="Tempo médio" description="Da confirmação à saída"><p class="op-figure">18 min</p></NuxtPageCard>
              <NuxtPageCard title="Valor do dia" description="Vendas confirmadas"><p class="op-figure">R$ 8.420,00</p></NuxtPageCard>
            </div>
            <NuxtTabs :items="tabs">
              <template #overview><NuxtAlert title="Operação ao vivo" description="A última leitura útil chegou agora." color="success" /></template>
              <template #activity><p class="op-body py-4">Atividade recente preservada no mesmo contexto.</p></template>
            </NuxtTabs>
          </section>

          <section id="splitter" class="space-y-4" data-operator-audit-id="catalog-splitter">
            <h2 class="op-title">Splitter canônico</h2>
            <OperatorSplitter id="catalog-splitter" persistence-key="catalog-demo" :items="splitter" class="h-80 rounded-md border">
              <template #list>
                <div class="h-full min-w-0 overflow-auto break-words p-2 [overflow-wrap:anywhere] sm:p-4" data-operator-pane data-pane-min="35">
                  <h3 class="op-title">Lista</h3><p class="op-body">Pane com min-width: 0 e limites do consumidor.</p>
                </div>
              </template>
              <template #detail>
                <div class="h-full min-w-0 overflow-auto break-words p-2 [overflow-wrap:anywhere] sm:p-4" data-operator-pane data-pane-min="25">
                  <h3 class="op-title">Detalhe</h3><p class="op-body">Persistência validada, ponteiro e teclado pertencem ao USplitter.</p>
                </div>
              </template>
            </OperatorSplitter>
          </section>

          <section id="form" class="grid gap-[var(--op-region-gap)] lg:grid-cols-[minmax(0,1fr)_20rem]" data-operator-audit-id="catalog-form">
            <NuxtCard>
              <template #header><h2 class="op-title">Formulário</h2></template>
              <NuxtForm :state="{}" class="space-y-4">
                <NuxtFormField label="Nome" description="Como aparece para o operador"><NuxtInput placeholder="Nome inequívoco" class="w-full" /></NuxtFormField>
                <NuxtFormField label="Contexto"><NuxtTextarea placeholder="Explique a necessidade" class="w-full" /></NuxtFormField>
                <div class="flex flex-wrap gap-[var(--op-control-gap)]" data-action-group>
                  <UiButton text="Salvar" />
                  <UiButton text="Cancelar" variant="outline" />
                </div>
              </NuxtForm>
            </NuxtCard>
            <NuxtPageAside>
              <h3 class="op-label">Sobre esta decisão</h3><p class="op-body text-muted">O aside permanece junto do formulário sem roubar a ação principal.</p>
            </NuxtPageAside>
          </section>

          <section id="table" class="space-y-4" data-operator-audit-id="catalog-table">
            <h2 class="op-title">Tabela e lista</h2>
            <NuxtTable :data="rows" />
          </section>

          <section id="states" class="space-y-4" data-operator-audit-id="catalog-states">
            <h2 class="op-title">Loading, vazio, erro e conteúdo extremo</h2>
            <div class="grid gap-4 md:grid-cols-2">
              <NuxtCard><div class="space-y-3" aria-label="Carregando"><NuxtSkeleton class="h-6 w-2/3" /><NuxtSkeleton class="h-20 w-full" /></div></NuxtCard>
              <NuxtEmpty title="Nada por aqui" description="Aplique outro filtro ou crie o primeiro item." icon="i-lucide-inbox" />
              <NuxtAlert title="Não foi possível atualizar" description="Tente novamente. O dado anterior continua identificado como desatualizado." color="error" />
              <NuxtCard><h3 class="op-title break-words">Conteúdo extremo não diminui a tipografia para caber</h3><p class="op-body break-words">Observação longa com consequência, responsável e próximo passo integralmente legíveis.</p></NuxtCard>
            </div>
          </section>

          <section class="space-y-4" data-operator-audit-id="catalog-overlays">
            <h2 class="op-title">Overlays</h2>
            <div class="flex flex-wrap gap-[var(--op-control-gap)]">
              <UiButton text="Abrir confirmação" @click="modalOpen = true" />
              <UiButton text="Ver shell operacional" variant="outline" to="?mode=operational" />
            </div>
            <UiModal v-model:open="modalOpen" title="Confirmar ação" description="A consequência aparece antes do gesto final.">
              <template #body><p class="op-body">O foco fica na camada superior e volta ao acionador.</p></template>
              <template #footer><UiButton text="Confirmar" /><UiButton text="Voltar" variant="outline" @click="modalOpen = false" /></template>
            </UiModal>
          </section>
        </OperatorPage>
      </OperatorOfficeShell>

      <section v-else data-operator-audit-id="catalog-operational-shell">
        <OperatorOperationalShell>
          <template #navigation><div class="w-[var(--op-rail-compact-width)] bg-rail" aria-label="Rail operacional" /></template>
          <template #header><OperatorPageHeader title="Shell operacional" /></template>
          <div class="p-[var(--op-page-inline-space)]">
            <NuxtCard>
              <h2 class="op-title">Tarefa de chão</h2>
              <p class="op-body">Chrome estável, conteúdo com min-width: 0 e barra de ação própria.</p>
              <UiButton class="mt-4" text="Voltar ao catálogo" variant="outline" to="/__operator_kit_catalog" />
            </NuxtCard>
          </div>
          <template #actions><UiToolbar><UiButton text="Concluir etapa" size="lg" /></UiToolbar></template>
        </OperatorOperationalShell>
      </section>
    </div>
  </OperatorAppRoot>
</template>

<style>
@import "./catalog.css";
</style>
