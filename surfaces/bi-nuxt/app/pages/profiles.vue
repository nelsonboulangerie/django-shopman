<script setup lang="ts">
// Perfis de consumo do balcão (BI-CONSUMPTION-PROFILES) — quem são os clientes,
// em três perfis PRESUMIDOS pela cesta: A só pra levar · B local + levar ·
// C só local. Entrega/iFood ficam fora da pergunta e dentro da conciliação.
//
// O híbrido (croissant, doce) não decide sozinho, então a tela mostra as três
// leituras (piso, vigente, teto) e quanto muda entre elas. O número honesto é a
// faixa; a leitura vigente é a que o explorador usa.
//
// Peças do kit (PR-B5 do WP-BI-CANON-LAUDO): período compacto e ⋯ no cabeçalho,
// frescor da leitura, `NuxtSelect` nos recortes, números em `OperatorMetric`, quadros
// em `OperatorReadingCard` (com CSV) e tabela sempre `NuxtTable`: a Conciliação soma
// no rodapé da tabela, a faixa honesta e a receita por categoria deixam de ser lista.
import type { BIProfileRange, BIProfileRow } from "~/generated/biContract";
import {
  readingChartCsv,
  type ReadingChartPoint,
  type ReadingChartSeries,
  type ReadingCsv,
} from "../../../operator-kit/app/presentation/readingChart";
import {
  delta,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  formatQty,
  rangeText,
  revpashHint,
  sensitivityHeadline,
  strikeMatrix,
  csvMoney,
} from "~/presentation/bi";

const { filters, report, freshness, pending, error, refresh, apply } = useBiProfiles();
const { selection, bounds, presets } = useBiWindow();
const shareItems = useBiShareMenuItems();
const { actions: readingActions, label: readingLabel } = useReadingPageActions(shareItems);

// ── Recortes ────────────────────────────────────────────────────────────────
// O `NuxtSelect` não aceita valor vazio: "todos" é `ALL` na tela e "" no contrato.
const ALL = "all";
const WEEKDAY_NAMES = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const weekdayItems = [
  { label: "Todos", value: ALL },
  ...WEEKDAY_NAMES.map((label, index) => ({ label, value: String(index) })),
];
const weekday = computed({
  get: () => filters.value.weekday || ALL,
  set: (value: string) => apply({ weekday: value === ALL ? "" : value }),
});

// Faixas do expediente (a última do contrato é "fora do expediente": entra na
// matriz como linha declarada, mas não vira opção de filtro).
const bands = computed(() => report.value?.bands ?? []);
const bandOptions = computed(() => bands.value.filter((b) => b.key !== "outside"));
const bandItems = computed(() => [
  { label: "Todas", value: ALL },
  ...bandOptions.value.map((band) => ({ label: band.title, value: band.key })),
]);
const hourBand = computed({
  get: () => filters.value.hour_band || ALL,
  set: (value: string) => apply({ hour_band: value === ALL ? "" : value }),
});
// Os recortes ativos (chips removíveis no celular, número no "Filtros").
const activeFilters = computed(() => [
  ...(weekday.value !== ALL
    ? [{ key: "weekday", label: `Dia: ${WEEKDAY_NAMES[Number(weekday.value)] ?? weekday.value}`, remove: () => (weekday.value = ALL) }]
    : []),
  ...(hourBand.value !== ALL
    ? [{
        key: "hour_band",
        label: `Faixa: ${bandItems.value.find((item) => item.value === hourBand.value)?.label ?? hourBand.value}`,
        remove: () => (hourBand.value = ALL),
      }]
    : []),
]);

// ── Leituras ────────────────────────────────────────────────────────────────
const readingRows = (reading: string): BIProfileRow[] =>
  (report.value?.profiles ?? []).filter((row) => row.reading === reading);
const currentRows = computed(() => readingRows("current"));
const previousByProfile = computed(() =>
  Object.fromEntries((report.value?.previous.rows ?? []).map((row) => [row.profile, row])),
);

// Coluna numérica alinha à direita, sem quebra; o número miúdo de apoio vai embaixo.
const NUM = { th: "whitespace-nowrap text-right", td: "whitespace-nowrap text-right tnum text-highlighted" } as const;
const LABEL = { td: "font-medium text-highlighted" } as const;

const readingColumns = [
  { accessorKey: "label", header: "Perfil", meta: { class: LABEL } },
  { id: "orders", header: "Pedidos", meta: { class: NUM } },
  { id: "revenue", header: "Receita", meta: { class: NUM } },
  { id: "ticket", header: "Ticket", meta: { class: NUM } },
  { id: "items", header: "Unidades · produtos por pedido", meta: { class: NUM } },
];
/** Linha "sem etiqueta" recua: é o resto, não um perfil. */
const readingMeta = {
  class: {
    tr: (row: { original: BIProfileRow }) => (row.original.profile === "unclassified" ? "text-muted" : ""),
  },
};
const readingCsv = (reading: string): ReadingCsv => ({
  header: ["Perfil", "Pedidos", "% dos pedidos", "Receita (R$)", "% da receita", "Ticket (R$)", "Unidades por pedido", "Produtos por pedido"],
  rows: readingRows(reading).map((row) => [
    row.label,
    row.orders,
    row.orders_share,
    csvMoney(row.revenue_q),
    row.revenue_share,
    csvMoney(row.average_ticket_q),
    row.units_per_order,
    row.distinct_per_order,
  ]),
});

// ── Estimativa ponderada por faixa ──────────────────────────────────────────
const seatedSeries: ReadingChartSeries[] = [{ key: "seated", label: "Comeu aqui", tone: "primary" }];
const seatedPoints = computed<ReadingChartPoint[]>(() => {
  const estimate = report.value?.estimate;
  return bandOptions.value.map((band, index) => {
    const orders = estimate?.orders_by_band[index] ?? 0;
    const seated = estimate?.seated_by_band[index] ?? 0;
    return {
      label: band.title,
      values: { seated: orders ? Math.round((seated * 1000) / orders) / 10 : null },
    };
  });
});

// ── A faixa honesta ─────────────────────────────────────────────────────────
const sensitivityColumns = [
  { accessorKey: "label", header: "Perfil", meta: { class: LABEL } },
  { id: "range", header: "Do piso ao teto", meta: { class: { td: "tnum text-highlighted" } } },
  { id: "current", header: "Vigente", meta: { class: NUM } },
  { id: "previous", header: "Período anterior", meta: { class: NUM } },
];
const currentShare = (profile: string) => currentRows.value.find((row) => row.profile === profile)?.orders_share ?? 0;
const sensitivityCsv = computed<ReadingCsv>(() => ({
  header: ["Perfil", "Pedidos no piso", "Pedidos no teto", "% no piso", "% no teto", "% vigente", "% no período anterior", "Pedidos no período anterior"],
  rows: (report.value?.sensitivity.ranges ?? []).map((range: BIProfileRange) => {
    const previous = previousByProfile.value[range.profile];
    return [
      range.label,
      range.min_orders,
      range.max_orders,
      range.min_share,
      range.max_share,
      currentShare(range.profile),
      previous?.orders_share ?? "",
      previous?.orders ?? "",
    ];
  }),
}));

// ── Conciliação: as parcelas e, no rodapé, o faturamento do recorte ─────────
interface ReconciliationRow {
  key: string;
  label: string;
  orders: number;
  revenue_q: number;
}
const reconciliationRows = computed<ReconciliationRow[]>(() =>
  report.value
    ? [
        { key: "counter", label: "Balcão (A, B, C e sem etiqueta)", orders: report.value.counter_orders, revenue_q: report.value.counter_revenue_q },
        { key: "delivery", label: "Entrega e iFood (fora da pergunta)", orders: report.value.delivery_orders, revenue_q: report.value.delivery_revenue_q },
      ]
    : [],
);
const totalOrders = computed(() => (report.value ? report.value.counter_orders + report.value.delivery_orders : 0));
const FOOT = "font-semibold text-highlighted";
const reconciliationColumns = computed(() => [
  {
    accessorKey: "label",
    header: "Origem",
    meta: { class: { td: "text-highlighted" } },
    footer: () => h("span", { class: FOOT }, "Faturamento do recorte"),
  },
  {
    id: "orders",
    header: "Pedidos",
    meta: { class: NUM },
    cell: ({ row }: { row: { original: ReconciliationRow } }) => formatInt(row.original.orders),
    footer: () => h("span", { class: `block text-right tnum ${FOOT}` }, formatInt(totalOrders.value)),
  },
  {
    id: "revenue",
    header: "Receita",
    meta: { class: NUM },
    cell: ({ row }: { row: { original: ReconciliationRow } }) => formatMoney(row.original.revenue_q),
    footer: () => h("span", { class: `block text-right tnum ${FOOT}` }, formatMoney(report.value?.revenue_total_q ?? 0)),
  },
]);
const reconciliationCsv = computed<ReadingCsv>(() => ({
  header: ["Origem", "Pedidos", "Receita (R$)"],
  rows: [
    ...reconciliationRows.value.map((row) => [row.label, row.orders, csvMoney(row.revenue_q)]),
    ["Faturamento do recorte", totalOrders.value, csvMoney(report.value?.revenue_total_q ?? 0)],
  ],
}));

// ── Matriz faixa × perfil, numa leitura por vez (começa na vigente) ─────────
const matrixReading = ref("current");
const readingItems = computed(() => (report.value?.readings ?? []).map((r) => ({ label: r.label, value: r.key })));
const matrixRows = computed(() => {
  const rows = readingRows(matrixReading.value);
  return bands.value.map((band, index) => {
    const total = rows.reduce((sum, row) => sum + (row.orders_by_band[index] ?? 0), 0);
    return {
      band,
      total,
      cells: rows.map((row) => ({
        profile: row.profile,
        orders: row.orders_by_band[index] ?? 0,
        share: total ? Math.round(((row.orders_by_band[index] ?? 0) * 1000) / total) / 10 : 0,
      })),
    };
  });
});
type MatrixRow = (typeof matrixRows.value)[number];
type MatrixCell = { row: { original: MatrixRow } };
// A célula lê de cima para baixo: a parcela da faixa (o que se compara) e, embaixo,
// quantos pedidos ela é. Antes a parcela vinha miúda entre parênteses, atrás do número.
const shareCell = (share: string, orders: string) =>
  h("span", { class: "flex flex-col items-end" }, [
    h("span", { class: "text-highlighted" }, share),
    h("span", { class: "text-xs text-muted" }, orders),
  ]);
const matrixColumns = computed(() => [
  {
    id: "band",
    header: "Faixa",
    meta: { class: LABEL },
    cell: ({ row }: MatrixCell) => row.original.band.title,
  },
  { id: "total", header: "Pedidos", meta: { class: NUM }, cell: ({ row }: MatrixCell) => formatInt(row.original.total) },
  ...currentRows.value.map((profile, index) => ({
    id: `profile-${profile.profile}`,
    header: profile.label,
    meta: { class: { th: "text-right", td: "whitespace-nowrap text-right tnum" } },
    cell: ({ row }: MatrixCell) => {
      const cell = row.original.cells[index];
      if (!cell || !row.original.total) return h("span", { class: "text-muted" }, "sem pedido");
      return shareCell(formatPercent(cell.share), `${formatInt(cell.orders)} ${cell.orders === 1 ? "pedido" : "pedidos"}`);
    },
  })),
]);
const matrixCsv = computed<ReadingCsv>(() => ({
  header: ["Faixa", "Pedidos", ...currentRows.value.flatMap((p) => [`${p.label}: pedidos`, `${p.label}: % da faixa`])],
  rows: matrixRows.value.map((row) => [row.band.title, row.total, ...row.cells.flatMap((c) => [c.orders, c.share])]),
}));

// ── Receita por categoria ───────────────────────────────────────────────────
const categoryRows = computed(() => (report.value?.categories ?? []).slice(0, 12));
const categoryColumns = [
  { accessorKey: "category", header: "Categoria", meta: { class: LABEL } },
  { id: "revenue", header: "Receita", meta: { class: NUM } },
  { id: "share", header: "Parcela", meta: { class: { th: "text-right", td: "w-2/5" } } },
];
const categoryCsv = computed<ReadingCsv>(() => ({
  header: ["Categoria", "Receita (R$)", "% da receita", "Bebida pronta industrializada (R$)"],
  rows: categoryRows.value.map((row) => [row.category, csvMoney(row.revenue_q), row.share, csvMoney(row.ready_beverage_q)]),
}));

// ── Bebida no pedido: dia da semana × faixa; o rodapé é o total por faixa ───
const strike = computed(() =>
  strikeMatrix(report.value?.beverage.by_weekday_band ?? [], bandOptions.value.map((b) => b.key)),
);
const strikeByBand = computed(() =>
  Object.fromEntries((report.value?.beverage.by_band ?? []).map((c) => [c.band, c])),
);
const strikeByWeekday = computed(() =>
  Object.fromEntries((report.value?.beverage.by_weekday ?? []).map((c) => [c.weekday, c])),
);
type StrikeRow = (typeof strike.value)[number];
type StrikeCell = { row: { original: StrikeRow } };
const rateOrNone = (cell?: { orders: number; rate: number } | null) =>
  cell && cell.orders ? formatPercent(cell.rate) : h("span", { class: "text-muted" }, "sem pedido");
const strikeColumns = computed(() => [
  {
    id: "weekday",
    header: "Dia",
    meta: { class: LABEL },
    cell: ({ row }: StrikeCell) => WEEKDAY_NAMES[row.original.weekday],
    footer: () => h("span", { class: FOOT }, "Todos os dias"),
  },
  ...bandOptions.value.map((band, index) => ({
    id: `band-${band.key}`,
    header: band.title,
    meta: { class: NUM },
    cell: ({ row }: StrikeCell) => rateOrNone(row.original.cells[index]),
    footer: () => h("span", { class: `block text-right tnum ${FOOT}` }, [rateOrNone(strikeByBand.value[band.key])]),
  })),
  {
    id: "day",
    header: "O dia todo",
    meta: { class: NUM },
    cell: ({ row }: StrikeCell) => rateOrNone(strikeByWeekday.value[row.original.weekday]),
  },
]);
const strikeCsv = computed<ReadingCsv>(() => ({
  header: ["Dia", ...bandOptions.value.map((b) => `${b.title}: % com bebida`), "O dia todo: % com bebida"],
  rows: strike.value.map((row) => [
    WEEKDAY_NAMES[row.weekday] ?? "",
    ...row.cells.map((c) => (c && c.orders ? c.rate : "")),
    strikeByWeekday.value[row.weekday]?.orders ? strikeByWeekday.value[row.weekday]!.rate : "",
  ]),
}));

// ── Receita por assento por hora ────────────────────────────────────────────
const revpashColumns = [
  { accessorKey: "title", header: "Faixa", meta: { class: LABEL } },
  { id: "revenue", header: "Receita local", meta: { class: NUM } },
  { id: "denominator", header: "Assentos × horas × dias", meta: { class: { th: "text-right", td: "text-right tnum text-muted" } } },
  { id: "revpash", header: "Por assento-hora", meta: { class: NUM } },
];
const revpashCsv = computed<ReadingCsv>(() => ({
  header: ["Faixa", "Receita local (R$)", "Assentos", "Horas", "Dias", "Receita por assento-hora (R$)"],
  rows: (report.value?.revpash ?? []).map((row) => [row.title, csvMoney(row.revenue_local_q), row.seats, row.hours, row.days, csvMoney(row.revpash_q)]),
}));
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Quem compra no balcão?" :actions="readingActions" :actions-label="readingLabel" :active-filters="activeFilters">
      <!-- Celular (regra da toolbar do kit): período e frescor na linha; dia da semana e
           faixa de hora no painel "Filtros", e o que estiver escolhido vira chip. -->
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
      <template #filters>
        <NuxtFormField label="Dia da semana" orientation="horizontal">
          <NuxtSelect v-model="weekday" :items="weekdayItems" class="w-36" data-bi-profiles-weekday />
        </NuxtFormField>
        <NuxtFormField label="Faixa de hora" orientation="horizontal">
          <NuxtSelect v-model="hourBand" :items="bandItems" class="w-44" data-bi-profiles-band />
        </NuxtFormField>
      </template>
      <template #filters-end>
        <ClientOnly>
          <ReadFreshness inline class="ms-auto" :metadata="freshness" :failed="Boolean(error)" />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <div class="flex flex-col gap-6">
      <NuxtAlert
        color="info"
        variant="subtle"
        icon="i-lucide-info"
        title="Perfil presumido pela cesta"
        description="Cada produto tem uma vocação (consome aqui, leva ou híbrido), editável em Configurações › Como vendemos. Entrega e iFood ficam fora da pergunta e dentro da conta. A hora é a do registro da venda."
      />

      <NuxtEmpty
        v-if="pending && !report"
        loading
        variant="naked"
        title="Lendo os pedidos de balcão"
        description="Perfis, faixas de hora e bebida do período escolhido."
        data-bi-loading
      />
      <OperatorScreenState
        v-if="error"
        state="error"
        what="os perfis"
        :description="report ? 'Os números na tela são os da leitura anterior.' : undefined"
        @retry="refresh()"
      />

      <template v-if="report">
        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <OperatorMetric
            title="Pedidos de balcão"
            :value="formatInt(report.counter_orders)"
            :delta="delta(report.counter_orders, report.previous.counter_orders)"
          />
          <OperatorMetric
            title="Faturamento de balcão"
            :value="formatMoneyCompact(report.counter_revenue_q)"
            :delta="delta(report.counter_revenue_q, report.previous.counter_revenue_q)"
          />
          <OperatorMetric
            title="Cobertura das etiquetas"
            :value="formatPercent(report.coverage)"
            hint="Pedidos com ao menos um produto etiquetado; o resto sai sem etiqueta"
          />
          <OperatorMetric
            title="Mudam de perfil do piso ao teto"
            :value="formatPercent(report.sensitivity.share_changed)"
            :hint="`${formatInt(report.sensitivity.orders_changed)} pedidos só com produtos ambíguos no que decide`"
          />
        </div>

        <!-- As três leituras, uma embaixo da outra: lado a lado, cada tabela tinha um
             terço da largura e cortava a Receita. -->
        <section class="flex flex-col gap-3" aria-labelledby="bi-readings-heading" data-bi-readings>
          <div>
            <p class="op-eyebrow text-muted">Perfis</p>
            <h2 id="bi-readings-heading" class="op-title text-highlighted">Os três perfis, em três leituras</h2>
            <p class="text-sm text-muted">
              Piso lê o ambíguo como levar; teto, como consumo local; vigente é a regra do explorador. Percentual
              sobre os pedidos e a receita de balcão do recorte.
            </p>
          </div>
          <OperatorReadingCard
            v-for="reading in report.readings"
            :key="reading.key"
            :title="reading.label"
            :heading-level="3"
            :csv="readingCsv(reading.key)"
            :data-bi-reading="reading.key"
          >
            <NuxtTable
              :data="readingRows(reading.key)"
              :columns="readingColumns"
              :meta="readingMeta"
              :get-row-id="(row) => row.profile"
              :caption="`Perfis na leitura ${reading.label}`"
            >
              <template #orders-cell="{ row }">
                {{ formatInt(row.original.orders) }}
                <span class="text-xs text-muted">{{ formatPercent(row.original.orders_share) }}</span>
              </template>
              <template #revenue-cell="{ row }">
                {{ formatMoneyCompact(row.original.revenue_q) }}
                <span class="text-xs text-muted">{{ formatPercent(row.original.revenue_share) }}</span>
              </template>
              <template #ticket-cell="{ row }">{{ formatMoney(row.original.average_ticket_q) }}</template>
              <template #items-cell="{ row }">{{ formatQty(row.original.units_per_order) }} · {{ formatQty(row.original.distinct_per_order) }}</template>
            </NuxtTable>
          </OperatorReadingCard>
        </section>

        <!-- Lado a lado só no 2xl: abaixo disso as quatro colunas da faixa honesta
             cortavam o período anterior. -->
        <div class="grid items-start gap-3 2xl:grid-cols-2">
          <OperatorReadingCard
            title="A faixa honesta"
            :description="sensitivityHeadline(report.sensitivity.orders_changed, report.sensitivity.share_changed, report.counter_orders)"
            :csv="sensitivityCsv"
            data-bi-sensitivity
          >
            <NuxtTable
              :data="report.sensitivity.ranges"
              :columns="sensitivityColumns"
              :get-row-id="(row) => row.profile"
              caption="Pedidos de cada perfil, do piso ao teto"
            >
              <template #range-cell="{ row }">{{ rangeText(row.original) }}</template>
              <template #current-cell="{ row }">{{ formatPercent(currentShare(row.original.profile)) }}</template>
              <template #previous-cell="{ row }">
                <template v-if="previousByProfile[row.original.profile]">
                  {{ formatPercent(previousByProfile[row.original.profile]!.orders_share) }}
                  <span class="text-xs text-muted">{{ formatInt(previousByProfile[row.original.profile]!.orders) }} pedidos</span>
                </template>
                <span v-else class="text-muted">sem base</span>
              </template>
            </NuxtTable>
          </OperatorReadingCard>

          <OperatorReadingCard
            title="Conciliação"
            description="A + B + C + sem etiqueta + entrega = faturamento do recorte. Sem filtros, é o mesmo número da aba Vendas."
            :csv="reconciliationCsv"
            data-bi-reconciliation
          >
            <NuxtTable
              :data="reconciliationRows"
              :columns="reconciliationColumns"
              :get-row-id="(row) => row.key"
              caption="Conciliação do faturamento do recorte"
            />
          </OperatorReadingCard>
        </div>

        <section class="flex flex-col gap-3" aria-labelledby="bi-estimate-heading" data-bi-estimate>
          <div>
            <p class="op-eyebrow text-muted">Estimativa ponderada</p>
            <h2 id="bi-estimate-heading" class="op-title text-highlighted">Quantos comeram aqui</h2>
            <p class="text-sm text-muted">
              A vocação em graus: cada produto tem um peso (a chance de ser consumido aqui, editável em Configurações ›
              Como vendemos) e a cesta vale o seu maior peso. É esperança sob os pesos vigentes, não medida; a faixa
              honesta continua sendo o que o dado garante.
            </p>
          </div>
          <div class="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <OperatorMetric
              title="Alguém comeu aqui"
              :value="`≈ ${formatInt(Math.round(report.estimate.seated_orders))}`"
              :hint="`${formatPercent(report.estimate.seated_share)} dos pedidos com peso · ${formatMoneyCompact(report.estimate.seated_revenue_q)} (${formatPercent(report.estimate.seated_revenue_share)} da receita)`"
              :delta="delta(report.estimate.seated_share, report.previous.estimate.seated_share)"
            />
            <OperatorMetric
              title="Só vieram buscar"
              :value="`≈ ${formatInt(Math.round(report.estimate.takeaway_orders))}`"
              :hint="`${formatPercent(report.estimate.takeaway_share)} dos pedidos com peso`"
            />
            <OperatorMetric
              title="Pedidos com peso"
              class="col-span-2 lg:col-span-1"
              :value="formatInt(report.estimate.weighted_orders)"
              :hint="report.estimate.unweighted_orders ? `${formatInt(report.estimate.unweighted_orders)} sem peso ficam fora desta conta` : 'Todos os pedidos de balcão entraram'"
            />
          </div>
          <OperatorReadingCard
            title="Comeu aqui, por faixa de hora"
            description="Percentual dos pedidos da faixa em que alguém comeu aqui"
            :heading-level="3"
            :csv="readingChartCsv('Faixa', seatedSeries, seatedPoints)"
            data-bi-seated-by-band
          >
            <OperatorReadingChart
              title="Comeu aqui, por faixa de hora"
              axis-label="Faixa"
              :series="seatedSeries"
              :points="seatedPoints"
              :format="formatPercent"
              :height="160"
              empty-title="Sem pedidos de balcão no recorte"
            />
          </OperatorReadingCard>
        </section>

        <OperatorReadingCard
          title="Perfil por faixa de hora"
          description="Parcela de cada perfil dentro da faixa e quantos pedidos ela é. Quem almoça às 13h e paga às 14h05 cai em Tarde."
          :csv="matrixCsv"
          data-bi-profile-matrix
        >
          <div class="flex flex-col gap-3">
            <NuxtFormField label="Leitura" orientation="horizontal" class="self-start">
              <NuxtSelect v-model="matrixReading" :items="readingItems" class="w-72 max-w-full" data-bi-matrix-reading />
            </NuxtFormField>
            <NuxtTable
              :data="matrixRows"
              :columns="matrixColumns"
              :get-row-id="(row) => row.band.key"
              caption="Pedidos por faixa de hora e perfil"
            />
          </div>
        </OperatorReadingCard>

        <section class="flex flex-col gap-3" aria-labelledby="bi-beverage-heading" data-bi-beverage>
          <div>
            <p class="op-eyebrow text-muted">Bebida no pedido</p>
            <h2 id="bi-beverage-heading" class="op-title text-highlighted">A bebida indica o perfil, mas não decide</h2>
            <p class="text-sm text-muted">Há C sem bebida (doce na mesa), e o café pra levar aumenta B e C.</p>
          </div>
          <div class="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <OperatorMetric
              title="Com bebida"
              :value="formatPercent(report.beverage.strike_rate)"
              :hint="`${formatInt(report.beverage.orders_with_beverage)} pedidos`"
            />
            <OperatorMetric title="Com café ou chá preparado" :value="formatPercent(report.beverage.prepared_rate)" />
            <OperatorMetric
              title="Bebidas por pedido local"
              :value="formatQty(report.beverage.per_local_order)"
              :hint="`${formatInt(report.beverage.local_orders)} pedidos com item local`"
            />
            <OperatorMetric
              title="Só bebida, nada mais"
              :value="formatPercent(report.beverage.beverage_only_share)"
              :hint="`${formatInt(report.beverage.beverage_only_orders)} pedidos · ticket ${formatMoney(report.beverage.beverage_only_ticket_q)} · medido, não estimado`"
            />
            <OperatorMetric
              title="Bebida pronta industrializada"
              class="col-span-2 lg:col-span-1"
              :value="formatMoney(report.beverage.ready_revenue_q)"
              :hint="`${formatPercent(report.beverage.ready_share)} do faturamento de balcão`"
            />
          </div>
          <OperatorReadingCard
            title="Pedidos com bebida, por dia e faixa"
            description="Percentual dos pedidos com bebida, no período inteiro"
            :heading-level="3"
            :csv="strikeCsv"
          >
            <NuxtTable
              :data="strike"
              :columns="strikeColumns"
              :get-row-id="(row) => String(row.weekday)"
              caption="Pedidos com bebida por dia da semana e faixa"
              data-bi-beverage-strike
            />
          </OperatorReadingCard>
        </section>

        <div class="grid items-start gap-3 2xl:grid-cols-2">
          <OperatorReadingCard
            title="Receita por categoria"
            :description="`Soma das linhas de balcão (histórico: categoria do Yooga; nativo: coleção do catálogo). Difere do faturamento por ${formatMoney(report.category_header_gap_q)} de desconto ou acréscimo de venda.`"
            :csv="categoryCsv"
            data-bi-categories
          >
            <NuxtTable
              :data="categoryRows"
              :columns="categoryColumns"
              :get-row-id="(row) => row.category"
              caption="Receita de balcão por categoria"
            >
              <template #category-cell="{ row }">
                <span class="flex flex-col">
                  <span>{{ row.original.category }}</span>
                  <span v-if="row.original.ready_beverage_q" class="text-xs font-normal text-muted">
                    bebida pronta: {{ formatMoney(row.original.ready_beverage_q) }}
                  </span>
                </span>
              </template>
              <template #revenue-cell="{ row }">{{ formatMoneyCompact(row.original.revenue_q) }}</template>
              <template #share-cell="{ row }">
                <span class="flex items-center gap-2">
                  <NuxtProgress :model-value="row.original.share" :max="100" class="flex-1" :aria-label="`${row.original.category}: ${formatPercent(row.original.share)} da receita`" />
                  <span class="w-12 text-right tnum text-highlighted">{{ formatPercent(row.original.share) }}</span>
                </span>
              </template>
              <template #empty>
                <NuxtEmpty variant="naked" icon="i-lucide-shopping-basket" title="Sem vendas de balcão no recorte" />
              </template>
            </NuxtTable>
          </OperatorReadingCard>

          <OperatorReadingCard
            title="Receita por assento por hora"
            :description="`Receita dos pedidos com item local ÷ (assentos × horas da faixa × dias com venda). Assentos: ${formatInt(report.seats)} (${report.seats_source}). Todas as faixas do recorte de dia da semana.`"
            :csv="revpashCsv"
            data-bi-revpash
          >
            <NuxtTable :data="report.revpash" :columns="revpashColumns" :get-row-id="(row) => row.band" caption="Receita por assento-hora por faixa">
              <template #revenue-cell="{ row }">{{ formatMoney(row.original.revenue_local_q) }}</template>
              <template #denominator-cell="{ row }">{{ revpashHint(row.original.seats, row.original.hours, row.original.days) }}</template>
              <template #revpash-cell="{ row }">{{ formatMoney(row.original.revpash_q) }}</template>
              <template #empty>
                <NuxtEmpty variant="naked" icon="i-lucide-armchair" title="Sem pedidos com item local no recorte" />
              </template>
            </NuxtTable>
          </OperatorReadingCard>
        </div>
      </template>
      </div>
    </main>
  </div>
</template>
