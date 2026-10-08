<script setup lang="ts">
// Explorar (F8/F9) — o gestor escolhe a pergunta: Métrica × Dimensão ×
// Cruzamento, e guarda o corte como cenário. Os selects nascem da gramática
// que viaja no relatório; combinação inválida nem chega ao servidor.
//
// Cenários são um select com grupos (Meus cenários / Exemplos) — escolher é
// um gesto só; as ações (salvar/favoritar/apagar) recuam para o menu ⋯.
import {
  EXPLORE_DIMENSION_LABELS,
  aggregateBucket,
  availableExamples,
  bucketLabel,
  bucketRows,
  formatExploreValue,
  shortDate,
} from "~/presentation/bi";

const { config, report, pending, errorDetail, apply } = useBiExplore();
const { views, save, toggleFavorite, remove } = useBiViews();
const { savedWindow, setPreset, applyCustom } = useBiWindow();

const currentSpec = computed(() =>
  report.value?.metrics.find((m) => m.key === config.value.metric),
);
const by2Options = computed(() =>
  (currentSpec.value?.dimensions ?? []).filter((d) => d !== "time" && d !== config.value.by),
);

// Exemplos = os fixos + os de contexto que a gramática do servidor declara
// suportar agora (feriado/clima só existem depois de injetados). Chip que
// abriria vazio não aparece.
const supportedDimensions = computed(() => [
  ...new Set((report.value?.metrics ?? []).flatMap((m) => m.dimensions)),
]);
const examples = computed(() => availableExamples(supportedDimensions.value));

// ── Cenários: seleção num select; "" = corte livre (—) ───────────────────────
const selectedScenario = ref("");

function applyScenario(next: { metric: string; by: string; by2: string; window?: Record<string, string> }) {
  apply({ metric: next.metric, by: next.by, by2: next.by2 ?? "" });
  const window = next.window ?? {};
  if (window.from && window.to) applyCustom(window.from, window.to);
  else if (window.preset) setPreset(window.preset);
}

function onScenarioChange(value: string) {
  selectedScenario.value = value;
  if (value.startsWith("view:")) {
    const view = views.value.find((v) => String(v.id) === value.slice(5));
    if (view) applyScenario(view.config);
  } else if (value.startsWith("example:")) {
    const example = examples.value.find((e) => e.name === value.slice(8));
    if (example) applyScenario({ ...example.config });
  }
}

// Mexer no corte à mão descola do cenário selecionado: virou corte livre.
function applyFree(next: Parameters<typeof apply>[0]) {
  selectedScenario.value = "";
  apply(next);
}

const loadedView = computed(() =>
  selectedScenario.value.startsWith("view:")
    ? views.value.find((v) => String(v.id) === selectedScenario.value.slice(5))
    : undefined,
);

// ── Menu ⋯: salvar / favoritar / apagar ──────────────────────────────────────
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

// Apagar pede confirmação (expansão desta migração): um cenário salvo apagado não
// volta, e antes o "Apagar" do menu agia no primeiro toque. A pergunta é a caixa da
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
  selectedScenario.value = "";
}

// ── Resultado: série, ranking ou tabela conforme o corte ────────────────────
const timeSeries = computed(() => {
  if (!report.value || report.value.dimension !== "time") return [];
  const rows = report.value.rows.map((row) => ({ date: row.key, value: row.value }));
  // `report.aggregation` e não uma soma incondicional: ticket médio, aproveitamento,
  // share e giro não se somam, e pico de salão se pega pelo maior — quem declara
  // é o servidor, no spec da métrica.
  const aggregation = report.value.aggregation;
  return bucketRows(rows).map((bucket) => ({
    label: bucketLabel(bucket.date, bucket.span),
    value: aggregateBucket(bucket.rows.map((r) => r.value), aggregation),
  }));
});

const resultTitle = computed(() => {
  if (!report.value) return "";
  const base = `${report.value.metric_label} por ${report.value.dimension_label.toLowerCase()}`;
  return report.value.dimension2 ? `${base} × ${report.value.dimension2_label.toLowerCase()}` : base;
});

// Cruzamento de duas dimensões: NuxtTable, o corpo inteiro do quadro (integrada ao
// cartão pelo tema do kit). Os cabeçalhos são os nomes que o servidor manda.
const crossColumns = computed(() => [
  { accessorKey: "label", header: report.value?.dimension_label ?? "", meta: { class: { td: "font-medium text-foreground" } } },
  { accessorKey: "label2", header: report.value?.dimension2_label ?? "", meta: { class: { td: "text-foreground" } } },
  { id: "value", header: report.value?.metric_label ?? "", meta: { class: { th: "text-right", td: "text-right tnum text-foreground" } } },
]);

const rankingRows = computed(() => {
  if (!report.value || report.value.dimension === "time" || report.value.dimension2) return [];
  return report.value.rows.map((row) => ({
    label: row.label,
    value: Math.abs(row.value),
    display: formatExploreValue(report.value!.unit, row.value),
  }));
});
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="O que você quer cruzar?">
      <template #status>
        <BiLiveStatus :pending="pending" :error="errorDetail" />
      </template>
      <template #actions>
        <BiWindowPicker class="max-md:hidden" />
        <BiPageMenu />
      </template>
      <template #phone-actions>
        <BiPeriodChip />
        <BiShareButton />
      </template>
    </OperatorPageHeader>
  <main class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pt-3 pb-4">
    <!-- O construtor: Cenário · Métrica · Dimensão · Cruzamento · ⋯ -->
    <NuxtCard as="section" aria-label="Construtor do cruzamento" data-bi-explore-builder>
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex flex-col gap-1 op-eyebrow text-muted-foreground">
          Cenário
          <UiNativeSelect
            :value="selectedScenario"
            class="min-w-44"
            @change="onScenarioChange(($event.target as HTMLSelectElement).value)"
          >
            <option value="">Nenhum (livre)</option>
            <optgroup v-if="views.length" label="Meus cenários">
              <option v-for="view in views" :key="view.id" :value="`view:${view.id}`">
                {{ view.is_favorite ? "★ " : "" }}{{ view.name }}
              </option>
            </optgroup>
            <optgroup label="Exemplos">
              <option v-for="example in examples" :key="example.name" :value="`example:${example.name}`">
                {{ example.name }}
              </option>
            </optgroup>
          </UiNativeSelect>
        </label>
        <NuxtSeparator orientation="vertical" class="h-10 self-end" />
        <label class="flex flex-col gap-1 op-eyebrow text-muted-foreground">
          Métrica
          <UiNativeSelect
            :value="config.metric"
            @change="applyFree({ metric: ($event.target as HTMLSelectElement).value })"
          >
            <option v-for="m in report?.metrics ?? []" :key="m.key" :value="m.key">{{ m.label }}</option>
          </UiNativeSelect>
        </label>
        <label class="flex flex-col gap-1 op-eyebrow text-muted-foreground">
          Dimensão
          <UiNativeSelect
            :value="config.by"
            @change="applyFree({ by: ($event.target as HTMLSelectElement).value })"
          >
            <option v-for="d in currentSpec?.dimensions ?? []" :key="d" :value="d">
              {{ EXPLORE_DIMENSION_LABELS[d] ?? d }}
            </option>
          </UiNativeSelect>
        </label>
        <label class="flex flex-col gap-1 op-eyebrow text-muted-foreground">
          Cruzamento
          <UiNativeSelect
            :value="config.by2"
            @change="applyFree({ by2: ($event.target as HTMLSelectElement).value })"
          >
            <option value="">Sem cruzamento</option>
            <option v-for="d in by2Options" :key="d" :value="d">
              {{ EXPLORE_DIMENSION_LABELS[d] ?? d }}
            </option>
          </UiNativeSelect>
        </label>

        <!-- O ⋯ do cenário: NuxtPopover (e não DropdownMenu) porque leva um campo de
             texto, o nome do cenário a salvar. Esc e clique fora fecham, do componente. -->
        <NuxtPopover v-model:open="menuOpen" :content="{ align: 'end', sideOffset: 8, collisionPadding: 8 }">
          <NuxtButton
            icon="i-lucide-ellipsis"
            color="neutral"
            variant="outline"
            square
            class="ml-auto self-end"
            aria-label="Ações do cenário"
            data-bi-scenario-menu
          />
          <template #content>
            <div class="grid w-72 gap-2 p-3" data-bi-scenario-panel>
              <p class="op-eyebrow text-muted-foreground">Salvar corte atual como cenário</p>
              <div class="flex items-center gap-2">
                <NuxtInput
                  v-model="saveName"
                  placeholder="Nome do cenário"
                  :maxlength="80"
                  class="min-w-0 flex-1"
                  aria-label="Nome do cenário"
                  @keydown.enter="saveScenario"
                />
                <NuxtButton label="Salvar" :disabled="!saveName.trim()" @click="saveScenario" />
              </div>
              <template v-if="loadedView">
                <NuxtSeparator class="my-1" />
                <NuxtButton
                  color="neutral"
                  variant="ghost"
                  block
                  class="justify-start"
                  :icon="loadedView.is_favorite ? 'i-lucide-star-off' : 'i-lucide-star'"
                  :label="loadedView.is_favorite ? 'Tirar dos favoritos' : 'Favoritar'"
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
    </NuxtCard>

    <BiPageState :pending="pending" />
    <NuxtAlert
      v-if="!pending && errorDetail"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      :title="errorDetail"
      role="alert"
      data-bi-explore-error
    />
    <template v-else-if="!pending && report">
      <BiSection :title="resultTitle" data-bi-explore-result>
        <template #caption>
          {{ shortDate(report.date_from) }} a {{ shortDate(report.date_to) }}
          <template v-if="report.truncated"> · Mostrando as {{ report.rows.length }} maiores; {{ report.truncated }} linhas ficaram fora</template>
        </template>

        <ChartBarSeries
          v-if="report.dimension === 'time' && !report.dimension2"
          :points="timeSeries"
          :format="(v) => formatExploreValue(report!.unit, v)"
        />
        <ChartHBarList v-else-if="rankingRows.length" :rows="rankingRows" />
        <NuxtTable
          v-else-if="report.rows.length"
          :data="report.rows"
          :columns="crossColumns"
          :get-row-id="(row) => `${row.key}|${row.key2}`"
          caption="Resultado do cruzamento"
        >
          <template #value-cell="{ row }">{{ formatExploreValue(report.unit, row.original.value) }}</template>
        </NuxtTable>
        <p v-else class="op-label text-muted-foreground">Nada no período para esse cruzamento.</p>
      </BiSection>
    </template>
  </main>
  </div>
</template>
