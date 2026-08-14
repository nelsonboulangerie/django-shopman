<script setup lang="ts">
// Explorar (F8/F9) — o gestor escolhe a pergunta: métrica × até duas
// dimensões, e salva o cruzamento como cenário. Os selects nascem da
// gramática que viaja no relatório; combinação inválida nem chega ao servidor.
import {
  EXPLORE_DIMENSION_LABELS,
  EXPLORE_EXAMPLES,
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

const saveName = ref("");
async function saveScenario() {
  const name = saveName.value.trim();
  if (!name) return;
  const window: Record<string, string> =
    selection.value.preset === "custom"
      ? { from: selection.value.from, to: selection.value.to }
      : { preset: selection.value.preset };
  if (await save(name, { ...config.value, window })) saveName.value = "";
}

function loadConfig(next: { metric: string; by: string; by2: string; window?: Record<string, string> }) {
  apply({ metric: next.metric, by: next.by, by2: next.by2 ?? "" });
  const window = next.window ?? {};
  if (window.from && window.to) applyCustom(window.from, window.to);
  else if (window.preset) setPreset(window.preset);
}

// Série temporal vira barras (agregação automática); ranking vira lista/tabela.
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
    <!-- Cenários salvos + exemplos de partida -->
    <div class="flex flex-wrap items-center gap-2">
      <template v-if="views.length">
        <span
          v-for="view in views"
          :key="view.id"
          class="group inline-flex h-9 items-center gap-1 rounded-md border border-border bg-card pl-3 pr-1 text-sm"
        >
          <button type="button" class="font-medium text-foreground" @click="loadConfig(view.config)">
            {{ view.name }}
          </button>
          <button
            type="button"
            :aria-label="view.is_favorite ? 'Tirar dos favoritos' : 'Favoritar'"
            class="rounded p-1"
            :class="view.is_favorite ? 'text-warning' : 'text-muted-foreground hover:text-foreground'"
            @click="toggleFavorite(view)"
          >
            <Icon :name="view.is_favorite ? 'lucide:star' : 'lucide:star-off'" class="size-4" />
          </button>
          <button
            type="button"
            aria-label="Apagar cenário"
            class="rounded p-1 text-muted-foreground hover:text-destructive"
            @click="remove(view)"
          >
            <Icon name="lucide:x" class="size-4" />
          </button>
        </span>
      </template>
      <template v-else>
        <span class="text-xs text-muted-foreground">Exemplos para começar:</span>
        <button
          v-for="example in EXPLORE_EXAMPLES"
          :key="example.name"
          type="button"
          class="inline-flex h-9 items-center rounded-md border border-border bg-card px-3 text-sm font-medium text-foreground"
          @click="loadConfig({ ...example.config })"
        >
          {{ example.name }}
        </button>
      </template>
    </div>

    <!-- O construtor: métrica × dimensões (form em card, inputs em background) -->
    <section class="flex flex-wrap items-end gap-3 rounded-md border border-border bg-card p-3">
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Métrica
        <select
          :value="config.metric"
          class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          @change="apply({ metric: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="m in report?.metrics ?? []" :key="m.key" :value="m.key">{{ m.label }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Por
        <select
          :value="config.by"
          class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          @change="apply({ by: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="d in currentSpec?.dimensions ?? []" :key="d" :value="d">
            {{ EXPLORE_DIMENSION_LABELS[d] ?? d }}
          </option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Cruzado com
        <select
          :value="config.by2"
          class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          @change="apply({ by2: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">(nada)</option>
          <option v-for="d in by2Options" :key="d" :value="d">
            {{ EXPLORE_DIMENSION_LABELS[d] ?? d }}
          </option>
        </select>
      </label>
      <div class="ml-auto flex items-end gap-2">
        <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          Salvar como cenário
          <input
            v-model="saveName"
            type="text"
            placeholder="Nome do cenário"
            maxlength="80"
            class="h-9 w-48 rounded-md border border-border bg-background px-2 text-sm text-foreground"
            @keydown.enter="saveScenario"
          />
        </label>
        <button
          type="button"
          class="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
          :disabled="!saveName.trim()"
          @click="saveScenario"
        >
          Salvar
        </button>
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
