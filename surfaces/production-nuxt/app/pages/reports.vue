<script setup lang="ts">
// Relatórios — a lente de GESTOR do Produção (perm fina
// backstage.view_production_reports; o gate grosso de chão NÃO abre esta tela).
// Três blocos, todos servidos pela API de relatórios:
//   · Gestão do dia: aproveitamento médio, capacidade % e a tabela de atrasos;
//   · Relatórios por período: Histórico · Produtividade · Desperdício, com
//     o painel de filtros único da suíte (`OperatorFilterPanel`: período, ficha,
//     posto, operador e os favoritos do gestor) e download CSV (link direto);
//   · Mapa código-cego ↔ preparo: a correlação que as telas de chão NUNCA
//     mostram (etiquetas circulam só com o código) — aqui é a visão de gestor.
// Sem gráficos: tabelas da suíte (`OperatorTable`) e números pré-formatados pelas
// projections. O filtro aplica ao mudar (fase 2: sem o cartão "Aplicar").
import { watchDebounced } from "@vueuse/core";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import { isStale, isoForOffset } from "~/presentation/production";
import {
  periodAnchor,
  periodLabel,
  periodOfDay,
  resolvePeriod,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";
import {
  REPORT_KINDS,
  REPORT_PERIOD_PRESETS,
  reportDimensions,
  reportPanelFilters,
  reportRecortesFromPanel,
  type ReportFiltersQuery,
} from "~/presentation/reports";
import type { ActiveFilters } from "../../../operator-kit/app/types/filters";

// ── Gestão do dia (KPIs + atrasos + mapa cego) ─────────────────────────────
// O "Período" do kit em Dia (Tipo 2): ‹ recua um dia; o futuro não tem gestão.
const todayISO = isoForOffset(0);
const selectedDate = ref(todayISO);
const managementPeriod = computed<PeriodSelection>({
  get: () => periodOfDay("day", selectedDate.value, todayISO),
  set: (next) => {
    selectedDate.value = periodAnchor(next, todayISO);
  },
});

const {
  management,
  lateOrders,
  forbidden: managementForbidden,
  pending: managementPending,
  refresh: refreshManagement,
} = useProductionManagement(selectedDate);
const blindMap = useBlindMap(selectedDate);

// ── Relatórios por período ─────────────────────────────────────────────────
const initialFilters: ReportFiltersQuery = {
  selected_only: true,
  report_kind: "history",
  date_from: isoForOffset(-6),
  date_to: isoForOffset(0),
  recipe_ref: "",
  position_ref: "",
  operator_ref: "",
  sort: "default",
  page_size: 50,
  cursor: "",
};
const {
  draft: filterDraft,
  applied: filters,
  validationError: filterError,
  isDirty: filtersDirty,
  selectKind,
  apply: applyFilters,
  openCursor,
} = useReportFilters(initialFilters);
const activeKind = computed(() => filters.value.report_kind);

// O intervalo do relatório é a Data do painel de filtros, com "Escolher as datas": os
// últimos 7 dias por padrão. Todo filtro aplica ao mudar; o operador digitado espera a
// pessoa parar de digitar.
const DEFAULT_REPORT_PERIOD: PeriodSelection = { preset: "7d", from: "", to: "" };
const reportPeriodSelection = ref<PeriodSelection>(DEFAULT_REPORT_PERIOD);
const reportPeriod = computed<PeriodSelection | undefined>({
  get: () => reportPeriodSelection.value,
  set: (next) => {
    reportPeriodSelection.value = next ?? DEFAULT_REPORT_PERIOD;
    const range = resolvePeriod(reportPeriodSelection.value, { today: todayISO, max: todayISO });
    filterDraft.date_from = range.date_from;
    filterDraft.date_to = range.date_to;
    applyFilters();
  },
});
watch(
  () => [filterDraft.recipe_ref, filterDraft.position_ref, filterDraft.sort],
  () => applyFilters(),
);
watchDebounced(
  () => filterDraft.operator_ref,
  () => applyFilters(),
  { debounce: 400 },
);
const exportEligible = computed(
  () => !filtersDirty.value && !filterError.value,
);

const {
  reports,
  pagination,
  historyRows,
  operatorRows,
  wasteRows,
  qualityRows,
  availableRecipes,
  availablePositions,
  forbidden: reportsForbidden,
  cursorStale,
  canExport,
  exportStatus,
  exportMessage,
  downloadCsv,
  cancelExport,
  pending,
  error,
  refresh,
} = useProductionReports(filters, exportEligible);

// 403 em qualquer bloco = mesma causa (sem a perm fina) → mensagem única e calma.
const forbidden = computed(
  () => reportsForbidden.value || managementForbidden.value,
);

const stale = computed(() =>
  isStale({ error: !!error.value, hasData: !!reports.value }),
);
const kindTabs = REPORT_KINDS.map((entry) => ({ value: entry.kind, label: entry.label }));
const reportKind = computed({
  get: () => activeKind.value,
  set: (kind: string) => {
    selectKind(kind as (typeof REPORT_KINDS)[number]["kind"]);
    applyFilters();
  },
});

// O período à vista sempre (o chip do painel só aparece fora do padrão).
const reportPeriodText = computed(() =>
  periodLabel(
    reportPeriodSelection.value,
    resolvePeriod(reportPeriodSelection.value, { today: todayISO, max: todayISO }),
    todayISO,
  ),
);

// Ficha técnica, posto e operador moram no painel de filtros (a lista da ficha ganha a
// busca sozinha quando cresce). Um favorito troca os três e o período de uma vez.
const panelDimensions = computed(() =>
  reportDimensions(availableRecipes.value, availablePositions.value),
);
const panelFilters = computed<ActiveFilters>({
  get: () => reportPanelFilters(filterDraft),
  set: (next) => Object.assign(filterDraft, reportRecortesFromPanel(next)),
});
const sortItems = computed(() => [
  { value: "default", label: "Ordem padrão" },
  ...(filterDraft.report_kind === "history"
    ? [
        { value: "date_desc", label: "Data mais recente" },
        { value: "date_asc", label: "Data mais antiga" },
      ]
    : []),
  { value: "name_asc", label: "Nome A–Z" },
  { value: "name_desc", label: "Nome Z–A" },
  { value: "quantity_desc", label: "Maior quantidade" },
  { value: "quantity_asc", label: "Menor quantidade" },
]);

// Colunas: a chave fica (fixada); as de apoio somem no celular por CSS.
const NUM = { class: { th: "text-right", td: "text-right tabular-nums whitespace-nowrap" } };
const SUPPORT_NUM = { ...NUM, supporting: true };
const lateColumns = [
  { id: "ref", header: "OP", enableHiding: false },
  { id: "product", header: "Produto" },
  { accessorKey: "elapsed_minutes", header: "Tempo (min)", meta: NUM },
  { accessorKey: "target_minutes", header: "Meta (min)", meta: SUPPORT_NUM },
  { id: "operator", header: "Operador", meta: { supporting: true } },
];
const historyColumns = [
  { id: "ref", header: "OP", enableHiding: false },
  { accessorKey: "date", header: "Data", meta: { supporting: true } },
  { accessorKey: "recipe_name", header: "Ficha técnica" },
  { id: "position", header: "Posto", meta: { supporting: true } },
  { accessorKey: "qty_planned", header: "Planejado", meta: SUPPORT_NUM },
  { id: "started", header: "Previsto", meta: SUPPORT_NUM },
  { id: "finished", header: "Realizado", meta: NUM },
  { accessorKey: "qty_loss", header: "Perda", meta: NUM },
  { id: "yield", header: "Aproveitamento", meta: SUPPORT_NUM },
  { id: "operator", header: "Operador", meta: { supporting: true } },
  { id: "duration", header: "Tempo (min)", meta: SUPPORT_NUM },
];
const operatorColumns = [
  { accessorKey: "operator_name", header: "Operador", enableHiding: false },
  { accessorKey: "wo_count", header: "Ordens", meta: NUM },
  { accessorKey: "qty_total", header: "Qtd realizada", meta: NUM },
  { id: "yield", header: "Aproveitamento médio", meta: SUPPORT_NUM },
  { id: "duration", header: "Tempo médio (min)", meta: SUPPORT_NUM },
];
const qualityColumns = [
  { accessorKey: "recipe_name", header: "Ficha técnica", enableHiding: false },
  { accessorKey: "grade_label", header: "Grau" },
  { id: "defect", header: "Defeito" },
  { accessorKey: "quantity", header: "Qtd", meta: NUM },
  { accessorKey: "share", header: "% da receita", meta: SUPPORT_NUM },
];
const wasteColumns = [
  { accessorKey: "recipe_name", header: "Ficha técnica", enableHiding: false },
  { accessorKey: "wo_count", header: "Ordens", meta: NUM },
  { accessorKey: "loss_total", header: "Perda total", meta: NUM },
  { id: "yield", header: "Aproveitamento médio", meta: SUPPORT_NUM },
];
const blindColumns = [
  { id: "code", header: "Código", enableHiding: false },
  { accessorKey: "name", header: "Preparo" },
  { accessorKey: "output_quantity_display", header: "Rendimento", meta: NUM },
];

// O aviso da tela mora no cabeçalho (`alerts`), sempre com a saída.
const screenAlerts = computed<OperatorScreenAlert[]>(() => {
  if (cursorStale.value)
    return [
      {
        id: "cursor",
        color: "warning",
        icon: "i-lucide-refresh-cw",
        title: "O relatório mudou enquanto você navegava.",
        description: "As páginas ficam paradas até reconciliar.",
        action: { label: "Reconciliar relatório", onSelect: () => applyFilters() },
      },
    ];
  if (stale.value)
    return [
      {
        id: "stale",
        color: "warning",
        icon: "i-lucide-wifi-off",
        title: "Sem atualizar: mostrando a última página aplicada.",
        action: { label: "Tentar de novo", onSelect: () => refresh() },
      },
    ];
  return [];
});
const exportTitle = computed(() =>
  exportStatus.value === "pending"
    ? "Exportação em andamento."
    : canExport.value
      ? undefined
      : "Corrija o período antes de baixar.",
);

function refreshAll() {
  refresh();
  refreshManagement();
  blindMap.refresh();
}
</script>


<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <ProductionHeader
      title="Relatórios"
      :searchable="false"
      :pending="pending || managementPending"
      :alerts="forbidden ? [] : screenAlerts"
      @refresh="refreshAll()"
    />

    <!-- Sem a perm fina de gestor: explica com calma, sem beco. -->
    <section v-if="forbidden" class="grid flex-1 place-items-center p-6">
      <NuxtEmpty
        icon="i-lucide-lock"
        title="Área do gestor"
        description="Os relatórios de produção pedem uma permissão de gestão que este operador não tem. Peça a liberação a quem administra a loja."
        :actions="[{ label: 'Voltar para a produção', to: '/', color: 'neutral', variant: 'outline' }]"
      />
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <!-- ── Gestão do dia ─────────────────────────────────────────────── -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="text-base font-semibold">Gestão do dia</h2>
        <OperatorPeriodPicker
          v-model="managementPeriod"
          :presets="['day']"
          :today="todayISO"
          :max="todayISO"
          label="Data da gestão"
          align="start"
        />
      </div>

      <div class="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4" data-reports-kpis>
        <OperatorMetric
          title="Aproveitamento médio"
          :value="management?.average_yield_rate || '—'"
          :hint="`Realizado ÷ previsto em ${management?.finished_orders ?? 0} lotes fechados`"
        />
        <OperatorMetric
          title="Capacidade"
          :value="management?.capacity_percent != null ? `${management.capacity_percent}%` : '—'"
          :hint="
            management?.capacity_percent != null
              ? 'Do planejado sobre a capacidade diária'
              : 'Sem capacidade configurada nas fichas'
          "
        />
        <OperatorMetric
          title="Planejado"
          :value="management?.planned_qty || '0'"
          :hint="`${management?.planned_orders ?? 0} lotes planejados`"
        />
        <OperatorMetric
          title="Perda"
          :value="management?.loss_qty || '0'"
          :hint="`Realizado ${management?.finished_qty || '0'} de ${management?.started_qty || '0'} previstos`"
        />
      </div>

      <div v-if="lateOrders.length" class="mb-4 grid gap-2" data-reports-late>
        <h3 class="flex items-center gap-2 text-sm font-semibold text-warning">
          <NuxtIcon name="i-lucide-timer" class="size-4" /> Atrasos em andamento
        </h3>
        <OperatorTable
          :data="lateOrders"
          :columns="lateColumns"
          :row-key="(row) => String(row.pk)"
          pinned="ref"
          caption="Lotes em andamento acima da meta de tempo"
        >
          <template #ref-cell="{ row }">
            <span class="font-mono text-xs">{{ row.original.ref }}</span>
          </template>
          <template #product-cell="{ row }">
            <span class="block font-medium">{{ row.original.recipe_name || row.original.output_sku }}</span>
            <span class="block text-xs text-muted-foreground">{{ row.original.output_sku }}</span>
          </template>
          <template #elapsed_minutes-cell="{ row }">
            <span class="font-semibold text-warning">{{ row.original.elapsed_minutes }}</span>
          </template>
          <template #operator-cell="{ row }">{{ row.original.operator_ref || "—" }}</template>
        </OperatorTable>
      </div>

      <!-- ── Relatórios por período ────────────────────────────────────── -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="text-base font-semibold">Relatórios</h2>
        <!-- Na mesa, as quatro abas; no celular elas não cabem sem cortar o rótulo, e a
             escolha vira lista (o CSS escolhe, sem esperar a hidratação). -->
        <NuxtTabs
          v-model="reportKind"
          :items="kindTabs"
          :content="false"
          variant="pill"
          class="max-sm:hidden"
          aria-label="Tipo de relatório"
          data-report-kind
        />
        <NuxtSelect
          v-model="reportKind"
          :items="kindTabs"
          value-key="value"
          class="w-44 sm:hidden"
          aria-label="Tipo de relatório"
        />
        <div class="ml-auto flex items-center gap-2">
          <NuxtButton
            icon="i-lucide-download"
            color="neutral"
            variant="outline"
            :label="exportStatus === 'pending' ? 'Exportando…' : 'Baixar CSV'"
            :loading="exportStatus === 'pending'"
            :disabled="!canExport"
            :title="exportTitle"
            @click="downloadCsv()"
          />
          <NuxtButton
            v-if="exportStatus === 'pending'"
            label="Cancelar"
            color="neutral"
            variant="ghost"
            @click="cancelExport()"
          />
        </div>
        <p
          v-if="exportMessage"
          class="basis-full text-right text-xs"
          :class="
            exportStatus === 'failure' || exportStatus === 'session_expired'
              ? 'text-error'
              : 'text-muted-foreground'
          "
          role="status"
          aria-live="polite"
        >
          {{ exportMessage }}
        </p>
      </div>

      <!-- O painel de filtros único (período, ficha, posto, operador e os favoritos); os
           recortes aplicam ao mudar, nada de "Aplicar". A ordem não é recorte: o seletor
           dela fica ao lado. -->
      <div class="mb-3 flex flex-wrap items-center gap-2" data-report-filters>
        <OperatorFilterPanel
          v-model="panelFilters"
          v-model:period="reportPeriod"
          :dimensions="panelDimensions"
          :period-presets="REPORT_PERIOD_PRESETS"
          custom-period
          :default-period="DEFAULT_REPORT_PERIOD"
          :today="todayISO"
          :max="todayISO"
          surface="production"
          screen="reports"
        />
        <NuxtSelect
          v-model="filterDraft.sort"
          :items="sortItems"
          value-key="value"
          icon="i-lucide-arrow-down-up"
          class="ms-auto w-48"
          aria-label="Ordenar"
          data-report-sort
        />
        <p
          id="report-date-help"
          role="status"
          aria-live="polite"
          class="basis-full text-xs"
          :class="filterError ? 'text-error' : 'text-muted-foreground'"
        >
          {{ filterError || `${reportPeriodText}. Período máximo: 93 dias.` }}
        </p>
      </div>

      <!-- Histórico por OP -->
      <OperatorTable
        v-if="activeKind === 'history'"
        :data="cursorStale ? [] : historyRows"
        :columns="historyColumns"
        :row-key="(row) => row.ref"
        :loading="pending && !reports"
        :error="Boolean(error) && !reports"
        what="os relatórios"
        empty-icon="i-lucide-table-2"
        :empty-title="cursorStale ? 'Navegação parada até reconciliar o relatório.' : 'Nenhum lote nesse período.'"
        :empty-description="cursorStale ? '' : 'Ajuste o período ou os filtros acima.'"
        pinned="ref"
        view-key="production-report-history"
        caption="Histórico por ordem de produção"
        @retry="refresh()"
      >
        <template #ref-cell="{ row }">
          <span class="font-mono text-xs">{{ row.original.ref }}</span>
        </template>
        <template #position-cell="{ row }">{{ row.original.position_ref || "—" }}</template>
        <template #started-cell="{ row }">
          {{ row.original.qty_started || "—" }}
          <!-- Fechamento sem abertura: o previsto não foi declarado, foi assumido igual
               ao planejado. A tela não o apresenta como fato. -->
          <NuxtBadge
            v-if="row.original.started_assumed"
            color="warning"
            class="ml-1"
            label="assumido"
            title="Fechado sem abertura: previsto assumido igual ao planejado"
          />
        </template>
        <template #finished-cell="{ row }">{{ row.original.qty_finished || "—" }}</template>
        <template #yield-cell="{ row }">{{ row.original.yield_rate || "—" }}</template>
        <template #operator-cell="{ row }">{{ row.original.operator_ref || "—" }}</template>
        <template #duration-cell="{ row }">{{ row.original.duration_minutes || "—" }}</template>
        <template v-if="historyRows.some((row) => row.started_assumed) || (pagination && pagination.total)" #footer>
          <p v-if="historyRows.some((row) => row.started_assumed)" class="mb-2 text-xs text-muted-foreground">
            <b class="font-medium text-warning">assumido</b>: o lote foi fechado sem abertura, e o
            previsto foi assumido igual ao planejado. Ninguém o declarou.
          </p>
          <ReportPagination
            v-if="pagination && pagination.total && !cursorStale"
            :pagination="pagination"
            :pending="pending"
            @open="openCursor"
          />
        </template>
      </OperatorTable>

      <!-- Produtividade por operador -->
      <OperatorTable
        v-else-if="activeKind === 'operator_productivity'"
        :data="cursorStale ? [] : operatorRows"
        :columns="operatorColumns"
        :row-key="(row) => row.operator_ref"
        :loading="pending && !reports"
        :error="Boolean(error) && !reports"
        what="os relatórios"
        empty-icon="i-lucide-table-2"
        :empty-title="cursorStale ? 'Navegação parada até reconciliar o relatório.' : 'Nenhum lote nesse período.'"
        :empty-description="cursorStale ? '' : 'Ajuste o período ou os filtros acima.'"
        view-key="production-report-operators"
        caption="Produtividade por operador"
        @retry="refresh()"
      >
        <template #yield-cell="{ row }">{{ row.original.yield_avg || "—" }}</template>
        <template #duration-cell="{ row }">{{ row.original.duration_avg_minutes || "—" }}</template>
        <template v-if="pagination && pagination.total && !cursorStale" #footer>
          <ReportPagination :pagination="pagination" :pending="pending" @open="openCursor" />
        </template>
      </OperatorTable>

      <!-- Qualidade: a partição do QC por receita × grau × defeito -->
      <OperatorTable
        v-else-if="activeKind === 'quality'"
        :data="cursorStale ? [] : qualityRows"
        :columns="qualityColumns"
        :row-key="(row) => `${row.recipe_ref}:${row.grade_ref}:${row.defect_ref}`"
        :loading="pending && !reports"
        :error="Boolean(error) && !reports"
        what="os relatórios"
        empty-icon="i-lucide-table-2"
        :empty-title="cursorStale ? 'Navegação parada até reconciliar o relatório.' : 'Nenhum lote nesse período.'"
        :empty-description="cursorStale ? '' : 'Ajuste o período ou os filtros acima.'"
        view-key="production-report-quality"
        caption="Qualidade por ficha, grau e defeito"
        @retry="refresh()"
      >
        <template #defect-cell="{ row }">{{ row.original.defect_label || "—" }}</template>
        <template v-if="pagination && pagination.total && !cursorStale" #footer>
          <ReportPagination :pagination="pagination" :pending="pending" @open="openCursor" />
        </template>
      </OperatorTable>

      <!-- Desperdício por ficha -->
      <OperatorTable
        v-else
        :data="cursorStale ? [] : wasteRows"
        :columns="wasteColumns"
        :row-key="(row) => row.recipe_ref"
        :loading="pending && !reports"
        :error="Boolean(error) && !reports"
        what="os relatórios"
        empty-icon="i-lucide-table-2"
        :empty-title="cursorStale ? 'Navegação parada até reconciliar o relatório.' : 'Nenhum lote nesse período.'"
        :empty-description="cursorStale ? '' : 'Ajuste o período ou os filtros acima.'"
        view-key="production-report-waste"
        caption="Desperdício por ficha técnica"
        @retry="refresh()"
      >
        <template #yield-cell="{ row }">{{ row.original.yield_avg || "—" }}</template>
        <template v-if="pagination && pagination.total && !cursorStale" #footer>
          <ReportPagination :pagination="pagination" :pending="pending" @open="openCursor" />
        </template>
      </OperatorTable>

      <!-- ── Mapa código-cego ↔ preparo (visão de gestor) ──────────────── -->
      <div class="mt-6 grid max-w-2xl gap-2" data-reports-blind-map>
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-base font-semibold">Mapa código-cego</h2>
          <NuxtBadge color="neutral" label="Visão de gestor" />
        </div>
        <p class="text-sm text-muted-foreground">
          As etiquetas de pesagem circulam pela cozinha apenas com o código do dia. Esta
          tabela é a única correlação código ↔ preparo, e ela não aparece nas telas de chão.
        </p>
        <OperatorTable
          :data="blindMap.rows.value"
          :columns="blindColumns"
          :row-key="(row) => row.code"
          empty-icon="i-lucide-tag"
          empty-title="Nenhum preparo aberto nesta data, então não há códigos para correlacionar."
          caption="Código do dia e preparo correspondente"
        >
          <template #code-cell="{ row }">
            <NuxtBadge color="primary" class="font-mono font-semibold tracking-wide" :label="row.original.code" />
          </template>
        </OperatorTable>
      </div>
    </section>
  </main>
</template>
