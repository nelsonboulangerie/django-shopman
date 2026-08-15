<script setup lang="ts">
// Explorar (F8/F9) — o gestor escolhe a pergunta: Métrica × Dimensão ×
// Cruzamento, e guarda o corte como cenário. Os selects nascem da gramática
// que viaja no relatório; combinação inválida nem chega ao servidor.
//
// Cenários são um select com grupos (Meus cenários / Exemplos) — escolher é
// um gesto só; as ações (salvar/favoritar/apagar) recuam para o menu ⋯.
import {
  EXPLORE_DIMENSION_LABELS,
  availableExamples,
  bucketLabel,
  bucketRows,
  formatExploreValue,
  shortDate,
} from "~/presentation/bi";

const { config, report, pending, errorDetail, apply } = useBiExplore();
const { views, save, toggleFavorite, remove } = useBiViews();
const { selection, setPreset, applyCustom } = useBiWindow();

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
  const window: Record<string, string> =
    selection.value.preset === "custom"
      ? { from: selection.value.from, to: selection.value.to }
      : { preset: selection.value.preset };
  if (await save(name, { ...config.value, window })) {
    saveName.value = "";
    menuOpen.value = false;
    const saved = views.value.find((v) => v.name === name);
    if (saved) selectedScenario.value = `view:${saved.id}`;
  }
}

async function removeLoaded() {
  if (!loadedView.value) return;
  await remove(loadedView.value);
  selectedScenario.value = "";
  menuOpen.value = false;
}

// ── Resultado: série, ranking ou tabela conforme o corte ────────────────────
const timeSeries = computed(() => {
  if (!report.value || report.value.dimension !== "time") return [];
  const rows = report.value.rows.map((row) => ({ date: row.key, value: row.value }));
  return bucketRows(rows).map((bucket) => ({
    label: bucketLabel(bucket.date, bucket.span),
    value: bucket.rows.reduce((sum, r) => sum + r.value, 0),
  }));
});

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
  <main class="flex flex-1 flex-col gap-4 p-4">
    <!-- O construtor: Cenário · Métrica · Dimensão · Cruzamento · ⋯ -->
    <section class="flex flex-wrap items-end gap-3 rounded-md border border-border bg-card p-3">
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Cenário
        <select
          :value="selectedScenario"
          class="h-9 min-w-44 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          @change="onScenarioChange(($event.target as HTMLSelectElement).value)"
        >
          <option value="">—</option>
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
        </select>
      </label>
      <div class="h-9 w-px self-end bg-border"></div>
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Métrica
        <select
          :value="config.metric"
          class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          @change="applyFree({ metric: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="m in report?.metrics ?? []" :key="m.key" :value="m.key">{{ m.label }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Dimensão
        <select
          :value="config.by"
          class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          @change="applyFree({ by: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="d in currentSpec?.dimensions ?? []" :key="d" :value="d">
            {{ EXPLORE_DIMENSION_LABELS[d] ?? d }}
          </option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Cruzamento
        <select
          :value="config.by2"
          class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          @change="applyFree({ by2: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">—</option>
          <option v-for="d in by2Options" :key="d" :value="d">
            {{ EXPLORE_DIMENSION_LABELS[d] ?? d }}
          </option>
        </select>
      </label>

      <div class="relative ml-auto self-end">
        <button
          type="button"
          class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-muted-foreground hover:text-foreground"
          aria-label="Ações do cenário"
          :aria-expanded="menuOpen"
          @click="menuOpen = !menuOpen"
        >
          <Icon name="lucide:ellipsis" class="size-4" />
        </button>
        <div
          v-if="menuOpen"
          class="absolute right-0 top-full z-20 mt-2 w-64 rounded-md border border-border bg-card p-3 shadow-md"
        >
          <p class="mb-2 text-xs font-medium text-muted-foreground">Salvar corte atual como cenário</p>
          <div class="flex items-center gap-2">
            <input
              v-model="saveName"
              type="text"
              placeholder="Nome do cenário"
              maxlength="80"
              class="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-sm text-foreground"
              @keydown.enter="saveScenario"
            />
            <button
              type="button"
              class="inline-flex h-9 shrink-0 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
              :disabled="!saveName.trim()"
              @click="saveScenario"
            >
              Salvar
            </button>
          </div>
          <template v-if="loadedView">
            <div class="my-3 border-t border-border"></div>
            <button
              type="button"
              class="flex h-9 w-full items-center gap-2 rounded-md px-2 text-sm text-foreground hover:bg-muted"
              @click="toggleFavorite(loadedView)"
            >
              <Icon :name="loadedView.is_favorite ? 'lucide:star-off' : 'lucide:star'" class="size-4" />
              {{ loadedView.is_favorite ? "Tirar dos favoritos" : "Favoritar" }}
            </button>
            <button
              type="button"
              class="flex h-9 w-full items-center gap-2 rounded-md px-2 text-sm text-destructive hover:bg-muted"
              @click="removeLoaded"
            >
              <Icon name="lucide:trash-2" class="size-4" />
              Apagar "{{ loadedView.name }}"
            </button>
          </template>
        </div>
      </div>
    </section>

    <p v-if="pending" class="text-sm text-muted-foreground">Carregando…</p>
    <p v-else-if="errorDetail" class="text-sm text-destructive">{{ errorDetail }}</p>
    <template v-else-if="report">
      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">
          {{ report.metric_label }} por {{ report.dimension_label.toLowerCase() }}<template v-if="report.dimension2"> × {{ report.dimension2_label.toLowerCase() }}</template>
        </h2>
        <p class="mb-3 text-xs text-muted-foreground">
          {{ shortDate(report.date_from) }} – {{ shortDate(report.date_to) }}
          <template v-if="report.truncated"> · Mostrando as {{ report.rows.length }} maiores; {{ report.truncated }} linhas ficaram fora</template>
        </p>

        <ChartBarSeries
          v-if="report.dimension === 'time' && !report.dimension2"
          :points="timeSeries"
          :format="(v) => formatExploreValue(report!.unit, v)"
        />
        <ChartHBarList v-else-if="rankingRows.length" :rows="rankingRows" />
        <table v-else-if="report.rows.length" class="w-full text-sm">
          <thead>
            <tr class="border-b border-border text-left text-xs font-medium text-muted-foreground">
              <th class="pb-2 font-medium">{{ report.dimension_label }}</th>
              <th class="pb-2 font-medium">{{ report.dimension2_label }}</th>
              <th class="pb-2 text-right font-medium">{{ report.metric_label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in report.rows"
              :key="`${row.key}|${row.key2}`"
              class="border-b border-border last:border-0"
            >
              <td class="py-2 pr-2 font-medium text-foreground">{{ row.label }}</td>
              <td class="py-2 pr-2 text-foreground">{{ row.label2 }}</td>
              <td class="py-2 text-right tabular-nums text-foreground">
                {{ formatExploreValue(report.unit, row.value) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="text-sm text-muted-foreground">Nada no período para esse cruzamento.</p>
      </section>
    </template>
  </main>
</template>
