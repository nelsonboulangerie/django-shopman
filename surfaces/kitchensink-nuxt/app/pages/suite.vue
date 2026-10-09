<script setup lang="ts">
// O shell de referência dos apps de operador, montado como um app de verdade monta:
// `OperatorSuiteShell` (barra lateral em três estados na mesa; ☰ e barra inferior de 3 a
// 5 vagas no celular), `OperatorPageHeader` com o ⋯ único e o aviso da tela (`alerts`),
// o conteúdo que rola e a ação na base (`OperatorActionBar`) entre o conteúdo e a barra
// inferior. No corpo, cada peça da fase 2 do kit com os seus estados
// (docs/plans/WP-FASE2-UX-OPERADOR.md). As peças que nascem no kit entram no catálogo do
// kit (`OperatorKitchenSinkScreenPieces`), que esta página reaproveita inteiro.
import type { OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";
import { readingMoneyFormat } from "../../../operator-kit/app/presentation/readingChart";
import {
  HOURLY_POINTS,
  HOURLY_SERIES,
  MADE_SOLD_POINTS,
  MADE_SOLD_SERIES,
  SUITE_ALERT_SCENARIOS,
  SUITE_SECTIONS,
  SUITE_SWIPE_ROWS,
  suiteAlerts,
  type SuiteAlertScenario,
} from "~/data/suiteReference";

const route = useRoute();
const router = useRouter();
const toast = useToast();
function said(label: string) {
  toast.add({ title: label, color: "success" });
}

// O cenário do aviso mora na URL (`?alerts=three`): o link colado abre o mesmo estado,
// e a matriz visual o abre direto.
const alertScenario = computed<SuiteAlertScenario>({
  get: () =>
    SUITE_ALERT_SCENARIOS.some(({ value }) => value === route.query.alerts)
      ? (route.query.alerts as SuiteAlertScenario)
      : "one",
  set: (value) => {
    void router.replace({ query: { ...route.query, alerts: value } });
  },
});
const alerts = computed(() => suiteAlerts(alertScenario.value, said));

const headerActions: OperatorHeaderAction[] = [
  { label: "Novo pedido", icon: "i-lucide-plus", priority: 1, onSelect: () => said("Novo pedido") },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => said("Atualizar") },
  { label: "Exportar CSV", icon: "i-lucide-download", onSelect: () => said("Exportar CSV") },
  {
    label: "Imprimir a fila",
    icon: "i-lucide-printer",
    disabled: true,
    reason: "Nenhuma impressora ligada a este dispositivo.",
  },
];

function swipeMenu(row: (typeof SUITE_SWIPE_ROWS)[number]) {
  return [
    ...(row.commit ? [{ label: row.commit.label, icon: "i-lucide-hand-helping", onSelect: () => said(row.commit!.label) }] : []),
    ...row.actions.map((action) => ({
      label: action.label,
      icon: action.icon.replace("lucide:", "i-lucide-"),
      color: action.tone === "danger" ? ("error" as const) : undefined,
      disabled: action.disabled,
      reason: action.disabled ? `O pedido ${row.ref} já foi pago e não pode ser recusado.` : undefined,
      onSelect: () => said(`${action.label} ${row.ref}`),
    })),
  ];
}

const acting = ref(false);
function act() {
  acting.value = true;
  setTimeout(() => {
    acting.value = false;
    said("Pedido 1048 pronto para retirar");
  }, 800);
}
const baseAction = computed(() => ({
  label: "Pronto para retirar",
  icon: "i-lucide-check",
  loading: acting.value,
  onSelect: act,
}));

const hydrated = ref(false);
onMounted(() => {
  hydrated.value = true;
});
</script>

<template>
  <div class="flex min-h-dvh" data-suite-reference :data-hydrated="hydrated">
    <OperatorSuiteShell
      storage-key="kitchensink-suite"
      :sections="SUITE_SECTIONS"
      label="Seções do shell de referência"
      operator-name="Ana Ferreira"
      @lock="said('Bloquear')"
      @select="(key) => said(`Seção de exemplo: ${key}`)"
    >
      <div class="flex min-h-0 flex-1 flex-col">
        <OperatorPageHeader
          title="Shell da suíte"
          search-placeholder="Buscar peça ou estado"
          :actions="headerActions"
          actions-label="Mais ações da tela"
          :alerts="alerts"
        >
          <template #status>
            <OperatorLiveStatus tone="calm" label="Atualiza sozinho a cada 30 s" detail="Fixtures locais" />
          </template>
          <template #filters-primary>
            <NuxtSelect
              v-model="alertScenario"
              :items="SUITE_ALERT_SCENARIOS"
              aria-label="Avisos da tela"
              class="w-40"
              data-suite-alert-scenario
            />
          </template>
          <template #filters-end>
            <span class="text-xs text-muted">Dados fixos</span>
          </template>
        </OperatorPageHeader>

        <main class="min-h-0 flex-1 overflow-y-auto" data-suite-content>
          <div class="mx-auto flex w-full max-w-[1120px] flex-col gap-8 px-4 pt-4 pb-6 sm:px-6">
            <section class="space-y-2" aria-labelledby="suite-shell-title" data-suite-shell-notes>
              <h2 id="suite-shell-title" class="text-xl font-semibold">O shell de referência</h2>
              <p class="text-sm text-muted">
                Esta página é a casca que todo app de operador veste. Na mesa, o botão no começo da barra do
                topo (ou a tecla C) passa a barra lateral por aberta, compacta e oculta. No celular, o ☰ abre a
                gaveta com o menu completo e a barra inferior guarda o menu rápido, de 3 a 5 vagas, com Mais
                quando sobra seção. O ⋯ do topo guarda as ações da tela; no celular, a ação de prioridade ganha
                vaga de ícone. O aviso da tela fica abaixo da barra: escolha o cenário em Avisos da tela.
              </p>
            </section>

            <!-- As peças que já moram no catálogo do kit: Mais ações, Anterior e próximo,
                 Ação na base e Estado da tela. -->
            <OperatorKitchenSinkScreenPieces />

            <section class="space-y-4" aria-labelledby="suite-swipe-title" data-suite-swipe>
              <div>
                <h2 id="suite-swipe-title" class="text-xl font-semibold">Deslizar</h2>
                <p class="text-sm text-muted">
                  OperatorSwipeRow: no toque, para a esquerda revela as ações e para a direita faz o gesto
                  principal depois do ponto de compromisso. O mouse não desliza: as mesmas ações moram no ⋯
                  de cada linha, que nunca deixa o deslizar ser a única porta.
                </p>
              </div>
              <NuxtCard>
                <div class="flex flex-col gap-2">
                  <OperatorSwipeRow
                    v-for="row in SUITE_SWIPE_ROWS"
                    :key="row.ref"
                    :label="`Pedido ${row.ref}`"
                    :actions="row.actions"
                    :commit="row.commit"
                    @pick="(key) => said(`${key} ${row.ref}`)"
                    @commit="said(row.commit?.label ?? '')"
                  >
                    <NuxtCard variant="soft">
                      <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                          <p class="text-base font-semibold">Pedido {{ row.ref }} · {{ row.customer }}</p>
                          <p class="text-sm text-muted">{{ row.detail }}</p>
                        </div>
                        <OperatorMoreMenu :items="swipeMenu(row)" :label="`Mais ações do pedido ${row.ref}`" />
                      </div>
                    </NuxtCard>
                  </OperatorSwipeRow>
                </div>
              </NuxtCard>
            </section>

            <section class="space-y-4" aria-labelledby="suite-chart-title" data-suite-stacked-chart>
              <div>
                <h2 id="suite-chart-title" class="text-xl font-semibold">Gráfico empilhado</h2>
                <p class="text-sm text-muted">
                  OperatorReadingChart com kind stacked, como no B.I.: partes do mesmo total. Deitado, para o
                  nome de cada produto caber inteiro; em pé, para uma série no tempo. Sem dados, o vazio da
                  própria peça.
                </p>
              </div>
              <div class="grid gap-4 lg:grid-cols-2">
                <OperatorReadingCard
                  title="Fez × vendeu"
                  description="Vendeu mais sobrou é o que a casa fez."
                >
                  <OperatorReadingChart
                    title="Fez × vendeu, produto a produto"
                    kind="stacked"
                    horizontal
                    axis-label="Produto"
                    :series="MADE_SOLD_SERIES"
                    :points="MADE_SOLD_POINTS"
                  />
                </OperatorReadingCard>
                <OperatorReadingCard
                  title="Faturamento por hora"
                  description="Balcão e entrega somam o faturamento da hora."
                >
                  <OperatorReadingChart
                    title="Faturamento por hora, por canal"
                    kind="stacked"
                    axis-label="Hora"
                    :series="HOURLY_SERIES"
                    :points="HOURLY_POINTS"
                    :format="readingMoneyFormat"
                  />
                </OperatorReadingCard>
                <OperatorReadingCard
                  title="Fez × vendeu, sem leitura"
                  description="O dia ainda não tem lote fechado."
                >
                  <OperatorReadingChart
                    title="Fez × vendeu, dia sem lote"
                    kind="stacked"
                    horizontal
                    axis-label="Produto"
                    :series="MADE_SOLD_SERIES"
                    :points="[]"
                    empty-title="Nenhum lote fechado hoje"
                  />
                </OperatorReadingCard>
              </div>
            </section>
            <MoreBelow />
          </div>
        </main>

        <!-- A ação na base mora aqui: em fluxo, depois do conteúdo que rola e antes da
             barra inferior do shell. Só abaixo de 1024 px. -->
        <OperatorActionBar
          :action="baseAction"
          context-label="Pedido 1048 · Ana Souza"
          context-value="R$ 48,70"
          data-suite-base-action
        />
      </div>
    </OperatorSuiteShell>
  </div>
</template>
