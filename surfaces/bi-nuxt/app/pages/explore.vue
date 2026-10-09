<script setup lang="ts">
// Explorar (F8/F9): o gestor escolhe a pergunta (Métrica × Dimensão × Cruzamento) e
// guarda o corte como cenário. As listas nascem da gramática que viaja no relatório;
// combinação inválida nem chega ao servidor.
//
// Cânon do kit (PR-B6 do WP-BI-CANON-LAUDO): cada escolha é um `NuxtFormField` com
// rótulo. Cenário (exemplos fixos mais os salvos, uma lista que cresce) e Métrica (a
// gramática inteira, duas dezenas) são `NuxtSelectMenu` com busca; Dimensão e
// Cruzamento (as poucas dimensões da métrica escolhida) são `NuxtSelect`. O resultado é
// o quadro do kit (`OperatorReadingCard`, com "Exportar CSV deste quadro"): a série no
// tempo é o `OperatorReadingChart`; ranking e cruzamento são `NuxtTable`.
import { useMediaQuery } from "@vueuse/core";
import { readingMoneyFormat } from "../../../operator-kit/app/presentation/readingChart";

import {
  aggregateBucket,
  availableExamples,
  bucketLabel,
  bucketRows,
  formatExploreValue,
} from "~/presentation/bi";
import {
  FREE_SCENARIO,
  NO_CROSS,
  crossItems,
  dimensionItems,
  exploreAxisLabel,
  exploreCsv,
  exploreResultDescription,
  scenarioMenuItems,
} from "~/presentation/explore";

const { config, report, freshness, pending, error, errorDetail, refresh, apply } = useBiExplore();
const { views, save, toggleFavorite, remove } = useBiViews();
const { selection, bounds, presets, savedWindow, setPreset, applyCustom } = useBiWindow();

// A busca da lista recebe o foco ao abrir só onde há teclado físico; no toque, o
// teclado virtual sobe quando a pessoa toca na busca (README do kit, "Escolha numa lista").
const touch = useMediaQuery("(pointer: coarse)");
const shareItems = useBiShareMenuItems();
const { actions: readingActions, label: readingLabel } = useReadingPageActions(shareItems);
// No celular o eixo do gráfico mostra menos datas, para os rótulos não se encostarem.
const wide = useMediaQuery("(min-width: 640px)");

const currentSpec = computed(() => report.value?.metrics.find((m) => m.key === config.value.metric));
const metricItems = computed(() => (report.value?.metrics ?? []).map((m) => ({ label: m.label, value: m.key })));
const byItems = computed(() => dimensionItems(currentSpec.value?.dimensions ?? []));
const by2Items = computed(() =>
  crossItems((currentSpec.value?.dimensions ?? []).filter((d) => d !== "time" && d !== config.value.by)),
);

// Exemplos = os fixos + os de contexto que a gramática do servidor declara suportar
// agora (feriado/clima só existem depois de injetados). Exemplo que abriria vazio não
// aparece.
const supportedDimensions = computed(() => [
  ...new Set((report.value?.metrics ?? []).flatMap((m) => m.dimensions)),
]);
const examples = computed(() => availableExamples(supportedDimensions.value));
const scenarioItems = computed(() => scenarioMenuItems(views.value, examples.value));

// ── Cenários: escolher é um gesto só; as ações recuam para o ⋯ ao lado ────────
const selectedScenario = ref(FREE_SCENARIO);

function applyScenario(next: { metric: string; by: string; by2: string; window?: Record<string, string> }) {
  apply({ metric: next.metric, by: next.by, by2: next.by2 ?? "" });
  const window = next.window ?? {};
  if (window.from && window.to) applyCustom(window.from, window.to);
  else if (window.preset) setPreset(window.preset);
}

function onScenarioChange(value: string | undefined) {
  if (!value) return;
  selectedScenario.value = value;
  if (value.startsWith("view:")) {
    const view = views.value.find((v) => String(v.id) === value.slice(5));
    if (view) applyScenario(view.query);
  } else if (value.startsWith("example:")) {
    const example = examples.value.find((e) => e.name === value.slice(8));
    if (example) applyScenario({ ...example.config });
  }
}

// Mexer no corte à mão descola do cenário escolhido: virou corte livre.
function applyFree(next: Parameters<typeof apply>[0]) {
  selectedScenario.value = FREE_SCENARIO;
  apply(next);
}

const crossValue = computed(() => config.value.by2 || NO_CROSS);
function onCrossChange(value: string) {
  applyFree({ by2: value === NO_CROSS ? "" : value });
}

const loadedView = computed(() =>
  selectedScenario.value.startsWith("view:")
    ? views.value.find((v) => String(v.id) === selectedScenario.value.slice(5))
    : undefined,
);

// ── O ⋯ do cenário: salvar / favoritar / apagar ───────────────────────────────
const menuOpen = ref(false);
const saveName = ref("");

async function saveScenario() {
  const name = saveName.value.trim();
  if (!name) return;
  if (await save(name, { ...config.value, window: savedWindow.value })) {
    saveName.value = "";
    menuOpen.value = false;
    const saved = views.value.find((v) => v.name === name);
    if (saved) selectedScenario.value = `view:${saved.id}`;
  }
}

// Apagar pede confirmação: um cenário salvo apagado não volta. A pergunta é a caixa da
// casa (`useConfirm` do kit), no tom de perda.
const confirmDelete = useConfirm();
const deleteLabel = computed(() => (loadedView.value ? `Apagar "${loadedView.value.name}"` : ""));

async function removeLoaded() {
  const view = loadedView.value;
  if (!view) return;
  menuOpen.value = false;
  const confirmed = await confirmDelete({
    title: `Apagar o cenário "${view.name}"?`,
    description: "O corte salvo some da lista de cenários e não volta. O que ele mostra continua no B.I.: dá para montar de novo e salvar.",
    confirmLabel: "Apagar cenário",
    cancelLabel: "Manter o cenário",
  });
  if (!confirmed) return;
  await remove(view);
  selectedScenario.value = FREE_SCENARIO;
}

// ── Resultado: série, ranking ou cruzamento conforme o corte ─────────────────
const isTimeSeries = computed(() => report.value?.dimension === "time" && !report.value.dimension2);

const timeBuckets = computed(() => {
  if (!report.value || !isTimeSeries.value) return [];
  return bucketRows(report.value.rows.map((row) => ({ date: row.key, value: row.value })));
});

// `report.aggregation` e não uma soma incondicional: ticket médio, aproveitamento,
// share e giro não se somam, e pico de salão se pega pelo maior. Quem declara é o
// servidor, no spec da métrica.
const timePoints = computed(() =>
  timeBuckets.value.map((bucket) => ({
    label: bucketLabel(bucket.date, bucket.span),
    values: { value: aggregateBucket(bucket.rows.map((r) => r.value), report.value?.aggregation ?? "sum") },
  })),
);
const timeAxisLabel = computed(() => exploreAxisLabel(timeBuckets.value[0]?.span ?? "day"));
const timeSeriesDef = computed(() => [{ key: "value", label: report.value?.metric_label ?? "" }]);

function formatValue(value: number): string {
  return formatExploreValue(report.value?.unit ?? "", value);
}

// O gráfico do kit recebe reais: dinheiro (`q`, centavos) é dividido ao montar os
// pontos e escrito pelo `readingMoneyFormat` (o eixo vira "R$ 15 mil" sozinho). O CSV
// segue dos pontos em centavos (`exploreCsv` converte).
const isMoney = computed(() => report.value?.unit === "q");
const chartPoints = computed(() =>
  isMoney.value
    ? timePoints.value.map((point) => ({
        ...point,
        values: { value: typeof point.values.value === "number" ? point.values.value / 100 : point.values.value },
      }))
    : timePoints.value,
);
const chartFormat = computed(() => (isMoney.value ? readingMoneyFormat : formatValue));

const resultTitle = computed(() => {
  if (!report.value) return "";
  const base = `${report.value.metric_label} por ${report.value.dimension_label.toLowerCase()}`;
  return report.value.dimension2 ? `${base} × ${report.value.dimension2_label.toLowerCase()}` : base;
});
const resultDescription = computed(() => (report.value ? exploreResultDescription(report.value) : ""));
const resultCsv = computed(() => {
  if (!report.value) return undefined;
  return exploreCsv(
    report.value,
    isTimeSeries.value ? { axisLabel: timeAxisLabel.value, points: timePoints.value } : undefined,
  );
});

// Ranking (uma dimensão que não é o tempo): a tabela com a barra do tamanho de cada
// linha (`NuxtProgress`) e o valor escrito ao lado; a barra sozinha não basta.
const rankingRows = computed(() => {
  if (!report.value || isTimeSeries.value || report.value.dimension2) return [];
  return report.value.rows.map((row) => ({ key: row.key, label: row.label, value: row.value }));
});
const rankingMax = computed(() => Math.max(...rankingRows.value.map((row) => Math.abs(row.value)), 1));
const rankingColumns = computed(() => [
  { accessorKey: "label", header: report.value?.dimension_label ?? "" },
  { id: "bar", header: "", meta: { class: { th: "w-2/5 max-sm:hidden", td: "w-2/5 max-sm:hidden" } } },
  { id: "value", header: report.value?.metric_label ?? "", meta: { class: { th: "text-right", td: "text-right tnum" } } },
]);

// Cruzamento de duas dimensões: os cabeçalhos são os nomes que o servidor manda.
const crossColumns = computed(() => [
  { accessorKey: "label", header: report.value?.dimension_label ?? "", meta: { class: { td: "font-medium" } } },
  { accessorKey: "label2", header: report.value?.dimension2_label ?? "" },
  { id: "value", header: report.value?.metric_label ?? "", meta: { class: { th: "text-right", td: "text-right tnum" } } },
]);

const emptyDescription = "Troque o período, a métrica ou a dimensão.";
const errorActions = computed(() => [
  {
    label: "Tentar de novo",
    icon: "i-lucide-refresh-cw",
    color: "error" as const,
    variant: "outline" as const,
    onClick: () => void refresh(),
  },
]);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="O que você quer cruzar?" :actions="readingActions" :actions-label="readingLabel">
      <!-- Celular: período e frescor são os dois primários; não há painel de filtros. -->
      <template #filters-primary>
        <OperatorPeriodPicker
          v-model="selection"
          :presets="presets"
          custom
          compact
          :today="bounds.today"
          :max="bounds.max"
          :epoch="bounds.epoch"
          align="start"
          label="Período de análise"
        />
      </template>
      <template #filters-end>
        <ClientOnly>
          <ReadFreshness inline class="ms-auto" :metadata="freshness" :failed="Boolean(error)" />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <!-- O construtor: Cenário (com o ⋯ das ações dele) · Métrica · Dimensão · Cruzamento -->
      <NuxtCard as="section" aria-label="Construtor do cruzamento" data-bi-explore-builder>
        <div class="flex flex-wrap items-end gap-3">
          <NuxtFormField label="Cenário" class="min-w-56 flex-1">
            <div class="flex items-center gap-2">
              <NuxtSelectMenu
                :model-value="selectedScenario"
                :items="scenarioItems"
                value-key="value"
                :search-input="{ autofocus: !touch, placeholder: 'Buscar cenário' }"
                class="min-w-0 flex-1"
                data-bi-scenario-select
                @update:model-value="onScenarioChange"
              />
              <!-- NuxtPopover (e não DropdownMenu) porque leva um campo de texto, o
                   nome do cenário a salvar. Esc e clique fora fecham, do componente. -->
              <NuxtPopover v-model:open="menuOpen" :content="{ align: 'end', sideOffset: 8, collisionPadding: 8 }">
                <NuxtButton
                  icon="i-lucide-ellipsis"
                  color="neutral"
                  variant="outline"
                  square
                  aria-label="Ações do cenário"
                  data-bi-scenario-menu
                />
                <template #content>
                  <div class="grid w-72 gap-2 p-3" data-bi-scenario-panel>
                    <NuxtFormField label="Salvar o corte atual como cenário">
                      <div class="flex items-center gap-2">
                        <NuxtInput
                          v-model="saveName"
                          placeholder="Nome do cenário"
                          :maxlength="80"
                          class="min-w-0 flex-1"
                          @keydown.enter="saveScenario"
                        />
                        <NuxtButton label="Salvar" :disabled="!saveName.trim()" @click="saveScenario" />
                      </div>
                    </NuxtFormField>
                    <template v-if="loadedView">
                      <NuxtSeparator class="my-1" />
                      <NuxtButton
                        color="neutral"
                        variant="ghost"
                        block
                        class="justify-start"
                        :icon="loadedView.pinned ? 'i-lucide-star-off' : 'i-lucide-star'"
                        :label="loadedView.pinned ? 'Tirar dos favoritos' : 'Favoritar'"
                        @click="toggleFavorite(loadedView)"
                      />
                      <NuxtButton
                        color="error"
                        variant="ghost"
                        block
                        class="justify-start"
                        icon="i-lucide-trash-2"
                        :label="deleteLabel"
                        @click="removeLoaded"
                      />
                    </template>
                  </div>
                </template>
              </NuxtPopover>
            </div>
          </NuxtFormField>
          <NuxtFormField label="Métrica" class="min-w-48 flex-1">
            <NuxtSelectMenu
              :model-value="metricItems.length ? config.metric : undefined"
              :items="metricItems"
              :disabled="!metricItems.length"
              placeholder="Sem opções nesta leitura"
              value-key="value"
              :search-input="{ autofocus: !touch, placeholder: 'Buscar métrica' }"
              class="w-full"
              data-bi-metric-select
              @update:model-value="(value?: string) => value && applyFree({ metric: value })"
            />
          </NuxtFormField>
          <NuxtFormField label="Dimensão" class="min-w-40 flex-1">
            <NuxtSelect
              :model-value="byItems.length ? config.by : undefined"
              :items="byItems"
              :disabled="!byItems.length"
              placeholder="Sem opções nesta leitura"
              class="w-full"
              data-bi-dimension-select
              @update:model-value="(value: string) => applyFree({ by: value })"
            />
          </NuxtFormField>
          <NuxtFormField label="Cruzamento" class="min-w-40 flex-1">
            <NuxtSelect
              :model-value="crossValue"
              :items="by2Items"
              :disabled="!byItems.length"
              class="w-full"
              data-bi-cross-select
              @update:model-value="onCrossChange"
            />
          </NuxtFormField>
        </div>
      </NuxtCard>

      <NuxtAlert
        v-if="!pending && error"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="errorDetail || 'Não deu para carregar o cruzamento.'"
        :actions="errorActions"
        orientation="horizontal"
        role="alert"
        data-bi-explore-error
      />
      <NuxtEmpty
        v-else-if="!report"
        loading
        icon="i-lucide-chart-no-axes-column"
        title="Carregando o cruzamento"
        data-bi-explore-loading
      />
      <OperatorReadingCard
        v-else
        :title="resultTitle"
        :description="resultDescription"
        :csv="resultCsv"
        data-bi-explore-result
      >
        <NuxtEmpty v-if="pending" loading variant="naked" title="Carregando o cruzamento" />
        <OperatorReadingChart
          v-else-if="isTimeSeries"
          :title="resultTitle"
          kind="bars"
          :axis-label="timeAxisLabel"
          :series="timeSeriesDef"
          :points="chartPoints"
          :format="chartFormat"
          :max-ticks="wide ? 6 : 4"
          empty-title="Nada no período para esse corte"
          :empty-description="emptyDescription"
        />
        <NuxtTable
          v-else-if="!report.dimension2"
          :data="rankingRows"
          :columns="rankingColumns"
          :get-row-id="(row) => row.key"
          :caption="resultTitle"
          data-bi-explore-ranking
        >
          <template #bar-cell="{ row }">
            <NuxtProgress
              :model-value="Math.abs(row.original.value)"
              :max="rankingMax"
              aria-hidden="true"
            />
          </template>
          <template #value-cell="{ row }">{{ formatValue(row.original.value) }}</template>
          <template #empty>
            <NuxtEmpty
              variant="naked"
              icon="i-lucide-chart-no-axes-column"
              title="Nada no período para esse corte"
              :description="emptyDescription"
            />
          </template>
        </NuxtTable>
        <NuxtTable
          v-else
          :data="report.rows"
          :columns="crossColumns"
          :get-row-id="(row) => `${row.key}|${row.key2}`"
          :caption="resultTitle"
          data-bi-explore-cross
        >
          <template #value-cell="{ row }">{{ formatValue(row.original.value) }}</template>
          <template #empty>
            <NuxtEmpty
              variant="naked"
              icon="i-lucide-chart-no-axes-column"
              title="Nada no período para esse cruzamento"
              :description="emptyDescription"
            />
          </template>
        </NuxtTable>
      </OperatorReadingCard>
    </main>
  </div>
</template>
