<script setup lang="ts">
// Produção: a âncora do B.I. Em cima, a pergunta nº 1 do dono (prévia
// `bi-sobra4.html`, LEITURA: pergunta, resposta, comparação, aprofundar): "Sobrou ou
// faltou ontem?", produto a produto, contra o mesmo dia da semana. Embaixo, os lotes
// no período: a série do que saiu do forno, o aproveitamento e o tempo REAL de forno
// (só o par armar→Concluir mede; a cobertura declara o resto, ADR-021 §4).
//
// Dois tempos na mesma tela, cada um no seu lugar: o DIA da leitura mora no cabeçalho
// (`?day=`), e a JANELA de análise mora no quadro dos lotes (`?period=`), que é onde
// ela vale. As outras telas do B.I. só têm a janela, e ela vai no cabeçalho delas.
import type { BIProductionReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  bucketLabel,
  bucketRows,
  coverageLabel,
  delta,
  formatInt,
  formatMinutes,
  formatQty,
  startedAssumedHint,
} from "~/presentation/bi";
import {
  VERDICTS,
  barScale,
  collectionsOf,
  compareCaption,
  filterRows,
  hiddenRowsSummary,
  historyHeading,
  overShortAnswer,
  overShortTitle,
  overUnit,
  planLabel,
  shortUnit,
  typicalLine,
  typicalName,
  verdictMeta,
} from "~/presentation/overShort";
import { todayIso } from "../../../operator-kit/app/presentation/dates";

// ── Sobrou ou faltou ─────────────────────────────────────────────────────────

const { report: day, pending: dayPending, error: dayError, refresh: dayRefresh, setDay } = useBiOverShort();

const today = todayIso();
const yesterday = computed(() => {
  const [y, m, d] = today.split("-").map(Number);
  return new Date(Date.UTC(y!, (m ?? 1) - 1, (d ?? 1) - 1)).toISOString().slice(0, 10);
});

// No celular a barra de 56px não comporta a pergunta com o dia: o dia já está no
// controle logo abaixo, então o título fica só com a pergunta (nunca cortado).
const isPhone = useMediaQuery("(max-width: 767.98px)");
const title = computed(() => {
  if (isPhone.value) return "Sobrou ou faltou?";
  return day.value ? overShortTitle(day.value.day, today) : "Sobrou ou faltou ontem?";
});

const query = ref("");
const verdict = ref("");
const collection = ref("");
const showAll = ref(false);
const openSku = ref<string | null>(null);
watch(() => day.value?.day, () => {
  openSku.value = null;
  showAll.value = false;
});

/** Linhas em foco antes do "+N produtos" (densidade pela atenção, SPEC4 §4). */
const FOCUS_ROWS = 8;
const rows = computed(() => day.value?.rows ?? []);
const filtered = computed(() =>
  filterRows(rows.value, { verdict: verdict.value, collection: collection.value, query: query.value }),
);
const narrowed = computed(() => Boolean(verdict.value || collection.value || query.value.trim()));
const visible = computed(() => (showAll.value || narrowed.value ? filtered.value : filtered.value.slice(0, FOCUS_ROWS)));
const hidden = computed(() => (showAll.value || narrowed.value ? [] : filtered.value.slice(FOCUS_ROWS)));
const scale = computed(() => barScale(rows.value));
const collections = computed(() => collectionsOf(rows.value));
const counts = computed(() => ({
  short: day.value?.summary.short ?? 0,
  over: day.value?.summary.over ?? 0,
  right: day.value?.summary.right ?? 0,
}));

/** Grade da tabela: um bloco de duas colunas no celular e no tablet; sete colunas no desktop largo. */
const COLUMNS =
  "grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,1.3fr)_104px_minmax(200px,230px)_92px_118px_minmax(0,1.1fr)_168px]";

const config = useRuntimeConfig().public as { productionUrl?: string };
const productionUrl = (config.productionUrl || "").replace(/\/?$/, "/");
const planUrl = computed(() => (day.value?.plan_day && productionUrl ? `${productionUrl}plan?date=${day.value.plan_day}` : ""));
const closeUrl = computed(() => (day.value && productionUrl ? `${productionUrl}close?date=${day.value.day}` : ""));
const { attrsFor } = useOperatorAppLink();
const planLink = computed(() => attrsFor(planUrl.value));

const shareQuery = computed(() => (day.value ? `?day=${day.value.day}` : ""));
const explainOpen = ref(false);

// Teclas do desktop: [ e ] andam um dia aberto; / leva à busca.
const search = ref<{ focus: () => void } | null>(null);
function typing(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  return Boolean(target?.closest("input, textarea, select, [contenteditable='true']"));
}
onKeyStroke("[", (event) => {
  if (typing(event) || !day.value?.previous_day) return;
  setDay(day.value.previous_day);
});
onKeyStroke("]", (event) => {
  if (typing(event) || !day.value?.next_day) return;
  setDay(day.value.next_day);
});
onKeyStroke("/", (event) => {
  if (typing(event)) return;
  event.preventDefault();
  search.value?.focus();
});

const CHIP_DOT = { short: "bg-destructive", over: "bg-warning", right: "bg-success" } as const;

// ── Os lotes no período (a janela de análise) ───────────────────────────────

const { report, pending, error, refresh } = useBiReport<BIProductionReport>("production");

const sum = (values: (string | number)[]) => values.reduce((total: number, v) => total + Number(v), 0);

const finishedSeries = computed(() => {
  const previous = report.value?.previous.finished_by_day ?? [];
  const rows = (report.value?.days ?? []).map((day, index) => ({
    ...day,
    prev_finished: Number(previous[index] ?? 0),
  }));
  return bucketRows(rows).map((bucket) => ({
    label: bucketLabel(bucket.date, bucket.span),
    value: sum(bucket.rows.map((d) => d.finished)),
    previous: sum(bucket.rows.map((d) => d.prev_finished)),
    detail: [
      BUCKET_SPAN_LABELS[bucket.span],
      `previsto ${formatQty(String(sum(bucket.rows.map((d) => d.started))))}`,
      `perda ${formatQty(String(sum(bucket.rows.map((d) => d.loss))))}`,
    ]
      .filter(Boolean)
      .join(" · "),
  }));
});

const yieldSeries = computed(() =>
  bucketRows(report.value?.days ?? []).map((bucket) => {
    const started = sum(bucket.rows.map((d) => d.started));
    const finished = sum(bucket.rows.map((d) => d.finished));
    return {
      label: bucketLabel(bucket.date, bucket.span),
      value: started ? Math.round((finished * 100) / started) : 0,
      detail: started
        ? [
            BUCKET_SPAN_LABELS[bucket.span],
            `cheio ${formatQty(String(sum(bucket.rows.map((d) => d.full_price))))}`,
            `desconto ${formatQty(String(sum(bucket.rows.map((d) => d.discounted))))}`,
          ]
            .filter(Boolean)
            .join(" · ")
        : "sem produção",
    };
  }),
);

const lossTotal = computed(() => (report.value?.days ?? []).reduce((total, d) => total + Number(d.loss), 0));
const finishedTotal = computed(() => (report.value?.days ?? []).reduce((total, d) => total + Number(d.finished), 0));
const startedTotal = computed(() => (report.value?.days ?? []).reduce((total, d) => total + Number(d.started), 0));

// Aproveitamento do período inteiro: realizado ÷ previsto (UX-PROD-AF).
const yieldPercent = (finished: number, started: number) => (started ? Math.round((finished * 100) / started) : 0);
const yieldTotal = computed(() => yieldPercent(finishedTotal.value, startedTotal.value));
const yieldPrevious = computed(() => {
  const prev = report.value?.previous;
  if (!prev) return 0;
  return yieldPercent(Number(prev.finished_total), Number(prev.started_total));
});

const ovenRows = (rows: BIProductionReport["oven_time_by_recipe"]) =>
  rows.map((row) => ({
    label: row.label,
    value: Number(row.avg_minutes),
    display: formatMinutes(row.avg_minutes),
    hint: `p90 ${formatMinutes(row.p90_minutes)} · armado ${formatMinutes(row.avg_planned_minutes)} · ${formatInt(row.runs)} ${row.runs === 1 ? "medição" : "medições"}`,
  }));
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader :title="title">
      <template #search>
        <OperatorSuiteSearch ref="search" v-model="query" screen-label="filtrando a tabela" placeholder="Buscar produto ou SKU" aria-label="Buscar produto ou SKU" />
      </template>
      <template #actions>
        <BiDayStepper
          v-if="day"
          :day="day.day"
          :today="today"
          :previous="day.previous_day"
          :next="day.next_day"
          :max="yesterday"
          @change="setDay"
        />
        <BiPageMenu v-slot="{ itemClass, close }">
          <button type="button" role="menuitem" :class="itemClass" @click="explainOpen = !explainOpen; close()">
            <Icon name="lucide:circle-help" class="size-4 text-muted-foreground" aria-hidden="true" />
            {{ explainOpen ? "Esconder como é calculado" : "Como é calculado" }}
          </button>
        </BiPageMenu>
        <a
          v-if="planUrl"
          :href="planUrl"
          :target="planLink.target"
          :rel="planLink.rel"
          class="inline-flex min-h-control items-center gap-2 rounded-md bg-primary px-4 op-label font-semibold text-primary-foreground transition hover:bg-primary/90"
          data-bi-plan-link
        >
          <Icon name="lucide:arrow-right-left" class="size-4" aria-hidden="true" />
          {{ planLabel(day?.plan_day ?? "") }}
        </a>
      </template>
      <template #phone-actions>
        <BiPhoneBell />
      </template>
      <template v-if="day" #filters>
        <span class="inline-flex min-h-control items-center gap-2 rounded-md border border-border bg-card px-3 op-label" data-bi-compare>
          <Icon name="lucide:git-compare-arrows" class="size-4 text-muted-foreground" aria-hidden="true" />
          <span class="font-normal text-muted-foreground">Comparar com:</span>
          <span class="font-semibold">{{ typicalName(day.day) }}</span>
          <span class="tnum font-normal text-muted-foreground">({{ compareCaption(day.day, day.compare_days) }})</span>
        </span>
        <span class="mx-1 h-6 w-px bg-border" aria-hidden="true" />
        <UiFilterChip :active="!verdict" :count="rows.length" :aria-pressed="!verdict" @click="verdict = ''">
          <template #icon><Icon v-if="!verdict" name="lucide:check" class="size-4 text-primary" aria-hidden="true" /></template>
          Todos
        </UiFilterChip>
        <UiFilterChip
          v-for="key in VERDICTS"
          :key="key"
          :active="verdict === key"
          :count="counts[key]"
          :aria-pressed="verdict === key"
          @click="verdict = verdict === key ? '' : key"
        >
          <template #icon><span class="size-2 rounded-full" :class="CHIP_DOT[key]" aria-hidden="true" /></template>
          {{ verdictMeta(key).label }}
        </UiFilterChip>
        <template v-if="collections.length">
          <span class="mx-1 h-6 w-px bg-border" aria-hidden="true" />
          <label
            class="relative inline-flex min-h-control items-center gap-2 rounded-full border px-3 op-label transition focus-within:ring-2 focus-within:ring-ring/40"
            :class="collection ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card'"
          >
            <Icon name="lucide:layers" class="size-4" aria-hidden="true" />
            Coleção: {{ collections.find((c) => c.ref === collection)?.name ?? "todas" }}
            <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
            <select v-model="collection" class="absolute inset-0 cursor-pointer opacity-0" aria-label="Coleção">
              <option value="">Todas as coleções</option>
              <option v-for="item in collections" :key="item.ref" :value="item.ref">{{ item.name }}</option>
            </select>
          </label>
        </template>
        <span class="hidden flex-1 lg:block" aria-hidden="true" />
        <span class="hidden items-center gap-1.5 op-micro text-muted-foreground lg:inline-flex" :title="'O dia da leitura mora no endereço: o link copiado abre esta mesma leitura.'">
          <Icon name="lucide:link" class="size-3.5" aria-hidden="true" />{{ shareQuery }}
        </span>
      </template>
    </OperatorPageHeader>

    <main class="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
      <BiPageState :pending="dayPending && !day" :error="dayError" what="a leitura do dia" @retry="dayRefresh()" />

      <template v-if="day">
        <div v-if="explainOpen" class="rounded-lg border border-border bg-card px-4 py-3 op-label leading-6" data-bi-explain>
          <p class="op-eyebrow text-muted-foreground">Como é calculado</p>
          <p><b>Fez</b>: o realizado dos lotes fechados do dia. <b>Vendeu</b>: as vendas do dia, de todos os canais.</p>
          <p><b>Acabou às</b>: a hora da venda em que o vendido alcançou o feito. <b>Vendas perdidas</b>: o ritmo até acabar, estendido até o fechamento{{ day.closes_at ? ` (${day.closes_at})` : "" }}, com teto de 2× o vendido. É a mesma conta que a sugestão do Planejamento usa.</p>
          <p><b>Faltou</b>: acabou antes da última hora. <b>Na medida</b>: acabou na última hora, sobrou até 2, ou vendeu mais do que fez (havia estoque de antes). <b>Sobrou</b>: sobrou mais que isso. O típico é a média dos últimos {{ day.compare_days.length || 4 }} dias iguais com a loja aberta.</p>
        </div>

        <!-- A resposta: uma frase e três números, cada um com o típico ao lado. -->
        <div class="grid gap-3 sm:grid-cols-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <BiAnswer :text="overShortAnswer(day)" class="sm:col-span-3 xl:col-span-1" />
          <StatTile label="Faltou" :value="formatInt(day.summary.short)" tone="destructive" :unit="shortUnit(day)" :hint="typicalLine(day, 'short')" />
          <StatTile label="Sobrou" :value="formatInt(day.summary.over)" tone="warning" :unit="overUnit(day)" :hint="typicalLine(day, 'over')" />
          <StatTile label="Na medida" :value="formatInt(day.summary.right)" tone="success" :unit="day.summary.right === 1 ? 'produto' : 'produtos'" :hint="typicalLine(day, 'right')" />
        </div>

        <div class="overflow-hidden rounded-lg border border-border bg-card" data-over-short-table>
          <div
            class="hidden h-10 items-center gap-3 border-b border-border bg-muted/60 px-4 op-eyebrow text-muted-foreground lg:grid"
            :class="COLUMNS"
            aria-hidden="true"
          >
            <div>Produto</div>
            <div>Veredito</div>
            <div class="flex items-center gap-3">
              Fez × vendeu
              <span class="inline-flex items-center gap-1 font-normal tracking-normal normal-case"><span class="h-3 w-0.5 bg-foreground" />típico</span>
            </div>
            <div>Acabou às</div>
            <div>{{ historyHeading(day.day, day.compare_days) }}</div>
            <div>Contra o típico</div>
            <div />
          </div>
          <template v-if="visible.length">
            <OverShortRow
              v-for="row in visible"
              :key="row.sku"
              :row="row"
              :scale="scale"
              :columns="COLUMNS"
              :open="openSku === row.sku"
              @toggle="openSku = openSku === row.sku ? null : row.sku"
            >
              <OverShortDetail :row="row" :day="day.day" :close-url="closeUrl" :plan-url="planUrl" :plan-label="planLabel(day.plan_day)" />
            </OverShortRow>
          </template>
          <p v-else-if="rows.length" class="px-4 py-4 op-body text-muted-foreground">Nenhum produto neste recorte.</p>
          <p v-else class="px-4 py-4 op-body text-muted-foreground">
            Nenhum lote fechado neste dia. A leitura começa quando a Produção fecha o primeiro lote.
          </p>
          <button
            v-if="hidden.length"
            type="button"
            class="flex min-h-11 w-full items-center gap-2 px-4 py-2 text-left op-label text-muted-foreground transition hover:bg-accent"
            data-over-short-more
            @click="showAll = true"
          >
            <Icon name="lucide:chevron-down" class="size-4 shrink-0" aria-hidden="true" />
            {{ hiddenRowsSummary(hidden) }}
          </button>
        </div>
      </template>

      <!-- Os lotes no período: a janela de análise do B.I. -->
      <section class="mt-2 flex flex-col gap-3" aria-labelledby="bi-lots-heading" data-bi-lots>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="bi-lots-heading" class="op-title">Como foram os lotes no período?</h2>
            <p class="op-micro text-muted-foreground">Aproveitamento, perda e tempo de forno na janela escolhida</p>
          </div>
          <BiWindowPicker />
        </div>
        <BiPageState :pending="pending && !report" :error="error" @retry="refresh()" />
        <template v-if="report">
          <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              label="Lotes fechados"
              :value="formatInt(report.batches_finished)"
              :delta="delta(report.batches_finished, report.previous.batches_finished)"
            />
            <StatTile
              label="Tempo de forno medido"
              :value="`${report.oven_coverage_percent}%`"
              :hint="coverageLabel(report.batches_measured, report.batches_finished)"
            />
            <StatTile
              label="Perda no período"
              :value="formatInt(lossTotal)"
              :delta="delta(lossTotal, Number(report.previous.loss_total), { downIsGood: true })"
              hint="Unidades que não saíram do forno"
            />
            <StatTile
              label="Aproveitamento do período"
              :value="`${yieldTotal}%`"
              :delta="delta(yieldTotal, yieldPrevious)"
              :hint="startedAssumedHint(report.batches_started_assumed, report.batches_finished)"
            />
          </div>

          <BiSection title="Produção por dia" caption="Unidades que saíram do forno; traço = período anterior; o detalhe traz previsto e perda">
            <ChartBarSeries :points="finishedSeries" :format="(v) => formatInt(v)" />
          </BiSection>

          <BiSection title="Aproveitamento por dia" caption="Realizado ÷ previsto, em %">
            <ChartBarSeries :points="yieldSeries" :format="(v) => `${v}%`" />
          </BiSection>

          <div class="grid gap-3 lg:grid-cols-2">
            <BiSection title="Tempo de forno por receita">
              <template #caption>
                Média medida (armar → Concluir) · {{ coverageLabel(report.batches_measured, report.batches_finished) }}
              </template>
              <ChartHBarList v-if="report.oven_time_by_recipe.length" :rows="ovenRows(report.oven_time_by_recipe)" />
              <p v-else class="op-body text-muted-foreground">Nenhuma medição no período ainda. O timer do forno alimenta este quadro.</p>
            </BiSection>
            <BiSection title="Tempo de forno por forno" caption="Lotes sem posição declarada ficam de fora deste corte">
              <ChartHBarList v-if="report.oven_time_by_oven.length" :rows="ovenRows(report.oven_time_by_oven)" />
              <p v-else class="op-body text-muted-foreground">Nenhuma medição com forno atribuído no período.</p>
            </BiSection>
          </div>
        </template>
      </section>
      <MoreBelow />
    </main>
  </div>
</template>
