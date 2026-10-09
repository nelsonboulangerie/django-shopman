<script setup lang="ts">
// Relatórios — a lente de GESTOR do Produção (perm fina
// backstage.view_production_reports; o gate grosso de chão NÃO abre esta tela).
// Três blocos, todos servidos pela API de relatórios:
//   · Gestão do dia: aproveitamento médio, capacidade % e a tabela de atrasos;
//   · Relatórios por período: Histórico · Produtividade · Desperdício, com
//     filtros (datas, ficha, posto, operador) e download CSV (link direto);
//   · Mapa código-cego ↔ preparo: a correlação que as telas de chão NUNCA
//     mostram (etiquetas circulam só com o código) — aqui é a visão de gestor.
// Sem gráficos: tabelas caladas e números pré-formatados pelas projections.
import { isStale, isoForOffset } from "~/presentation/production";
import {
  periodAnchor,
  periodOfDay,
  resolvePeriod,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";
import { REPORT_KINDS, type ReportFiltersQuery } from "~/presentation/reports";

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

// O intervalo do relatório é o "Período" do kit (Tipo 2) com personalizado: os
// últimos 7 dias por padrão, ‹ › andam um período igual, e a troca já aplica (o
// resto do filtro continua esperando o "Aplicar").
const reportPeriod = ref<PeriodSelection>({ preset: "7d", from: "", to: "" });
function changeReportPeriod(next: PeriodSelection) {
  reportPeriod.value = next;
  const range = resolvePeriod(next, { today: todayISO, max: todayISO });
  filterDraft.date_from = range.date_from;
  filterDraft.date_to = range.date_to;
  applyFilters();
}
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

const hasRows = computed(() => {
  if (activeKind.value === "operator_productivity")
    return operatorRows.value.length > 0;
  if (activeKind.value === "recipe_waste") return wasteRows.value.length > 0;
  if (activeKind.value === "quality") return qualityRows.value.length > 0;
  return historyRows.value.length > 0;
});
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: !!reports.value }),
);
function changeReportKind(reportKind: (typeof REPORT_KINDS)[number]["kind"]) {
  selectKind(reportKind);
  applyFilters();
}

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
      @refresh="refreshAll()"
    />

    <!-- Sem a perm fina de gestor: explica com calma, sem beco. -->
    <section
      v-if="forbidden"
      class="grid flex-1 place-items-center p-6 text-center"
    >
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Área do gestor</p>
        <p class="text-sm text-muted-foreground">
          Os relatórios de produção pedem uma permissão de gestão que este
          operador não tem. Peça a liberação a quem administra a loja.
        </p>
        <NuxtLink
          to="/"
          class="mt-1 text-sm text-primary underline-offset-2 hover:underline"
          >Voltar para a produção</NuxtLink
        >
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <!-- ── Gestão do dia ─────────────────────────────────────────────── -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="op-title">Gestão do dia</h2>
        <OperatorPeriodPicker
          v-model="managementPeriod"
          :presets="['day']"
          :today="todayISO"
          :max="todayISO"
          label="Data da gestão"
          align="start"
        />
        <span v-if="management" class="text-sm text-muted-foreground">{{
          management.selected_date_display
        }}</span>
      </div>

      <div class="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div class="rounded-md border bg-card p-3">
          <p
            class="text-xs font-medium uppercase tracking-wider text-muted-foreground"
          >
            Aproveitamento médio
          </p>
          <p class="mt-1 text-xl font-bold tabular-nums">
            {{ management?.average_yield_rate || "—" }}
          </p>
          <p class="text-xs text-muted-foreground">
            Realizado ÷ previsto em
            {{ management?.finished_orders ?? 0 }} lotes fechados
          </p>
        </div>
        <div class="rounded-md border bg-card p-3">
          <p
            class="text-xs font-medium uppercase tracking-wider text-muted-foreground"
          >
            Capacidade
          </p>
          <p class="mt-1 text-xl font-bold tabular-nums">
            <template v-if="management?.capacity_percent != null"
              >{{ management.capacity_percent }}%</template
            >
            <template v-else>—</template>
          </p>
          <p class="text-xs text-muted-foreground">
            {{
              management?.capacity_percent != null
                ? "Do planejado sobre a capacidade diária"
                : "Sem capacidade configurada nas fichas"
            }}
          </p>
        </div>
        <div class="rounded-md border bg-card p-3">
          <p
            class="text-xs font-medium uppercase tracking-wider text-muted-foreground"
          >
            Planejado
          </p>
          <p class="mt-1 text-xl font-bold tabular-nums">
            {{ management?.planned_qty || "0" }}
          </p>
          <p class="text-xs text-muted-foreground">
            {{ management?.planned_orders ?? 0 }} lotes planejados
          </p>
        </div>
        <div class="rounded-md border bg-card p-3">
          <p
            class="text-xs font-medium uppercase tracking-wider text-muted-foreground"
          >
            Perda
          </p>
          <p class="mt-1 text-xl font-bold tabular-nums">
            {{ management?.loss_qty || "0" }}
          </p>
          <p class="text-xs text-muted-foreground">
            Realizado {{ management?.finished_qty || "0" }} de
            {{ management?.started_qty || "0" }} previstos
          </p>
        </div>
      </div>

      <div
        v-if="lateOrders.length"
        class="mb-4 overflow-hidden rounded-md border"
      >
        <p
          class="flex items-center gap-2 border-b bg-warning/10 px-3 py-2 text-sm font-semibold text-warning"
        >
          <Icon name="lucide:timer" class="size-4" /> Atrasos em andamento
        </p>
        <table class="w-full text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">OP</th>
              <th class="px-3 py-2 font-semibold">Produto</th>
              <th class="px-3 py-2 text-right font-semibold">Tempo (min)</th>
              <th class="px-3 py-2 text-right font-semibold">Meta (min)</th>
              <th class="px-3 py-2 font-semibold">Operador</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-for="item in lateOrders" :key="item.pk">
              <td class="px-3 py-2 font-mono text-xs">{{ item.ref }}</td>
              <td class="px-3 py-2">
                <p class="font-medium">
                  {{ item.recipe_name || item.output_sku }}
                </p>
                <p class="text-xs text-muted-foreground">
                  {{ item.output_sku }}
                </p>
              </td>
              <td
                class="px-3 py-2 text-right tabular-nums font-semibold text-warning"
              >
                {{ item.elapsed_minutes }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ item.target_minutes }}
              </td>
              <td class="px-3 py-2">{{ item.operator_ref || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ── Relatórios por período ────────────────────────────────────── -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="text-lg font-semibold">Relatórios</h2>
        <div
          class="flex items-center gap-1 rounded-md border bg-background p-0.5"
          role="group"
          aria-label="Tipo de relatório"
        >
          <!-- Segmento compacto de relatório; preserva a leitura de abas mutuamente exclusivas. -->
          <button
            v-for="entry in REPORT_KINDS"
            :key="entry.kind"
            type="button"
            class="min-h-8 rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              activeKind === entry.kind
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="activeKind === entry.kind"
            @click="changeReportKind(entry.kind)"
          >
            {{ entry.label }}
          </button>
        </div>
        <UiButton
          type="button"
          variant="outline"
          size="sm"
          class="ml-auto min-h-8"
          :disabled="!canExport"
          :title="
            exportStatus === 'pending'
              ? 'Exportação em andamento.'
              : canExport
                ? undefined
                : 'Aplique os filtros válidos antes de baixar.'
          "
          @click="downloadCsv()"
        >
          <Icon name="lucide:download" class="size-4" />
          {{ exportStatus === "pending" ? "Exportando…" : "Baixar CSV" }}
        </UiButton>
        <UiButton
          v-if="exportStatus === 'pending'"
          type="button"
          variant="ghost"
          size="sm"
          class="min-h-8"
          @click="cancelExport()"
        >
          Cancelar
        </UiButton>
        <p
          v-if="exportMessage"
          class="basis-full text-right text-xs text-muted-foreground"
          :class="{
            'text-destructive':
              exportStatus === 'failure' || exportStatus === 'session_expired',
          }"
          role="status"
          aria-live="polite"
        >
          {{ exportMessage }}
        </p>
      </div>

      <div
        class="mb-3 flex flex-wrap items-end gap-3 rounded-md border bg-card p-3"
      >
        <div class="grid gap-1 text-xs font-medium text-muted-foreground">
          Período
          <OperatorPeriodPicker
            :model-value="reportPeriod"
            :presets="['day', 'week', 'month', '7d', '28d']"
            custom
            :today="todayISO"
            :max="todayISO"
            label="Período do relatório"
            align="start"
            @update:model-value="changeReportPeriod"
          />
        </div>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Ficha técnica
          <UiNativeSelect v-model="filterDraft.recipe_ref" class="w-auto">
            <option value="">Todas</option>
            <option
              v-for="recipe in availableRecipes"
              :key="recipe.ref"
              :value="recipe.ref"
            >
              {{ recipe.name }}
            </option>
          </UiNativeSelect>
        </label>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Posto
          <UiNativeSelect v-model="filterDraft.position_ref" class="w-auto">
            <option value="">Todos</option>
            <option
              v-for="position in availablePositions"
              :key="position.ref"
              :value="position.ref"
            >
              {{ position.name }}
            </option>
          </UiNativeSelect>
        </label>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Operador
          <UiInput
            v-model="filterDraft.operator_ref"
            type="text"
            placeholder="Nome ou usuário"
            class="w-auto"
          />
        </label>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Ordenar
          <UiNativeSelect v-model="filterDraft.sort" class="w-auto">
            <option value="default">Padrão</option>
            <option
              v-if="filterDraft.report_kind === 'history'"
              value="date_desc"
            >
              Data mais recente
            </option>
            <option
              v-if="filterDraft.report_kind === 'history'"
              value="date_asc"
            >
              Data mais antiga
            </option>
            <option value="name_asc">Nome A–Z</option>
            <option value="name_desc">Nome Z–A</option>
            <option value="quantity_desc">Maior quantidade</option>
            <option value="quantity_asc">Menor quantidade</option>
          </UiNativeSelect>
        </label>
        <UiButton
          type="button"
          size="sm"
          class="min-h-8"
          :disabled="!!filterError"
          @click="applyFilters()"
        >
          Aplicar
        </UiButton>
        <p
          id="report-date-help"
          role="status"
          aria-live="polite"
          class="basis-full text-xs"
          :class="filterError ? 'text-destructive' : 'text-muted-foreground'"
        >
          {{
            filterError ||
            "Período máximo: 93 dias. O período vale na hora; os outros filtros, ao aplicar."
          }}
        </p>
      </div>

      <div
        v-if="cursorStale"
        role="alert"
        aria-live="assertive"
        class="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-warning"
      >
        <Icon name="lucide:refresh-cw" class="size-4 shrink-0" />
        <span>O relatório mudou enquanto você navegava.</span>
        <UiButton
          type="button"
          size="sm"
          variant="outline"
          class="ml-auto min-h-8"
          @click="applyFilters()"
        >
          Reconciliar relatório
        </UiButton>
      </div>

      <div
        v-if="stale && !cursorStale"
        role="status"
        aria-live="polite"
        class="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-warning"
      >
        <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
        <span>Sem atualizar: mostrando a última página aplicada.</span>
      </div>

      <div
        v-if="cursorStale"
        class="grid place-items-center rounded-md border border-dashed border-warning/40 py-12 text-center text-sm text-muted-foreground"
      >
        Navegação bloqueada até reconciliar o relatório.
      </div>
      <p
        v-else-if="pending && !reports"
        class="text-sm text-muted-foreground"
      >
        Carregando…
      </p>
      <div
        v-else-if="error && !reports"
        class="grid place-items-center gap-2 rounded-md border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">
          Não foi possível carregar os relatórios.
        </p>
        <UiButton
          type="button"
          variant="outline"
          size="sm"
          class="mt-1 min-h-8"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" />
          Tentar de novo
        </UiButton>
      </div>
      <div
        v-else-if="!hasRows"
        class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:table-2" class="size-8" />
        <p class="text-base font-medium">Nenhum lote nesse período.</p>
        <p class="text-sm">Ajuste as datas ou os filtros acima.</p>
      </div>

      <!-- Histórico por OP -->
      <div
        v-else-if="activeKind === 'history'"
        class="overflow-x-auto rounded-md border"
      >
        <table class="w-full min-w-[64rem] text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">OP</th>
              <th class="px-3 py-2 font-semibold">Data</th>
              <th class="px-3 py-2 font-semibold">Ficha técnica</th>
              <th class="px-3 py-2 font-semibold">Posto</th>
              <th class="px-3 py-2 text-right font-semibold">Planejado</th>
              <th class="px-3 py-2 text-right font-semibold">Previsto</th>
              <th class="px-3 py-2 text-right font-semibold">Realizado</th>
              <th class="px-3 py-2 text-right font-semibold">Perda</th>
              <th class="px-3 py-2 text-right font-semibold">
                Aproveitamento
              </th>
              <th class="px-3 py-2 font-semibold">Operador</th>
              <th class="px-3 py-2 text-right font-semibold">Tempo (min)</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="row in historyRows"
              :key="row.ref"
              class="hover:bg-muted/30"
            >
              <td class="px-3 py-2 font-mono text-xs">{{ row.ref }}</td>
              <td class="px-3 py-2 tabular-nums">{{ row.date }}</td>
              <td class="px-3 py-2 font-medium">{{ row.recipe_name }}</td>
              <td class="px-3 py-2">{{ row.position_ref || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.qty_planned }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.qty_started || "—" }}
                <!-- Fechamento sem abertura: o previsto não foi declarado, foi
                     assumido igual ao planejado. A tela não o apresenta como fato. -->
                <span
                  v-if="row.started_assumed"
                  class="ml-1 rounded-sm border border-warning/40 bg-warning/10 px-1 text-xs font-medium text-warning"
                  title="Fechado sem abertura: previsto assumido igual ao planejado"
                  >assumido</span
                >
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.qty_finished || "—" }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.qty_loss }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.yield_rate || "—" }}
              </td>
              <td class="px-3 py-2">{{ row.operator_ref || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.duration_minutes || "—" }}
              </td>
            </tr>
          </tbody>
        </table>
        <p
          v-if="historyRows.some((row) => row.started_assumed)"
          class="border-t px-3 py-2 text-xs text-muted-foreground"
        >
          <b class="font-medium text-warning">assumido</b>: o lote foi fechado
          sem abertura, e o previsto foi assumido igual ao planejado. Ninguém o
          declarou.
        </p>
      </div>

      <!-- Produtividade por operador -->
      <div
        v-else-if="activeKind === 'operator_productivity'"
        class="overflow-x-auto rounded-md border"
      >
        <table class="w-full text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">Operador</th>
              <th class="px-3 py-2 text-right font-semibold">Ordens</th>
              <th class="px-3 py-2 text-right font-semibold">Qtd realizada</th>
              <th class="px-3 py-2 text-right font-semibold">
                Aproveitamento médio
              </th>
              <th class="px-3 py-2 text-right font-semibold">
                Tempo médio (min)
              </th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="row in operatorRows"
              :key="row.operator_ref"
              class="hover:bg-muted/30"
            >
              <td class="px-3 py-2 font-medium">{{ row.operator_name }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.wo_count }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.qty_total }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.yield_avg || "—" }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.duration_avg_minutes || "—" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Qualidade: a partição do QC por receita × grau × defeito -->
      <div
        v-else-if="activeKind === 'quality'"
        class="overflow-x-auto rounded-md border"
      >
        <table class="w-full text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">Ficha técnica</th>
              <th class="px-3 py-2 font-semibold">Grau</th>
              <th class="px-3 py-2 font-semibold">Defeito</th>
              <th class="px-3 py-2 text-right font-semibold">Qtd</th>
              <th class="px-3 py-2 text-right font-semibold">% da receita</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="row in qualityRows"
              :key="`${row.recipe_ref}:${row.grade_ref}:${row.defect_ref}`"
              class="hover:bg-muted/30"
            >
              <td class="px-3 py-2 font-medium">{{ row.recipe_name }}</td>
              <td class="px-3 py-2">{{ row.grade_label }}</td>
              <td class="px-3 py-2">{{ row.defect_label || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.quantity }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.share }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Desperdício por ficha -->
      <div v-else class="overflow-x-auto rounded-md border">
        <table class="w-full text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">Ficha técnica</th>
              <th class="px-3 py-2 text-right font-semibold">Ordens</th>
              <th class="px-3 py-2 text-right font-semibold">Perda total</th>
              <th class="px-3 py-2 text-right font-semibold">
                Aproveitamento médio
              </th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="row in wasteRows"
              :key="row.recipe_ref"
              class="hover:bg-muted/30"
            >
              <td class="px-3 py-2 font-medium">{{ row.recipe_name }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.wo_count }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.loss_total }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.yield_avg || "—" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <nav
        v-if="pagination && pagination.total && !cursorStale"
        class="mt-3 flex items-center justify-between gap-3 text-sm"
        aria-label="Paginação do relatório"
      >
        <span class="text-muted-foreground" role="status" aria-live="polite">
          Exibindo {{ pagination.from }}–{{ pagination.to }} de
          {{ pagination.total }} resultado{{
            pagination.total === 1 ? "" : "s"
          }}
        </span>
        <div class="flex gap-2">
          <UiButton
            type="button"
            size="sm"
            variant="outline"
            class="min-h-8"
            :disabled="!pagination.previous_cursor || pending"
            @click="openCursor(pagination.previous_cursor)"
          >
            Anterior
          </UiButton>
          <UiButton
            type="button"
            size="sm"
            variant="outline"
            class="min-h-8"
            :disabled="!pagination.next_cursor || pending"
            @click="openCursor(pagination.next_cursor)"
          >
            Próxima
          </UiButton>
        </div>
      </nav>

      <!-- ── Mapa código-cego ↔ preparo (visão de gestor) ──────────────── -->
      <div class="mt-6">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <h2 class="text-lg font-semibold">Mapa código-cego</h2>
          <UiBadge variant="outline" class="px-1.5 py-0 text-xs"
            >Visão de gestor</UiBadge
          >
        </div>
        <p class="mb-3 max-w-2xl text-sm text-muted-foreground">
          As etiquetas de pesagem circulam pela cozinha apenas com o código do
          dia. Esta tabela é a única correlação código ↔ preparo, e ela não
          aparece nas telas de chão.
        </p>
        <div
          v-if="!blindMap.rows.value.length"
          class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
        >
          Nenhum preparo aberto nesta data, então não há códigos para correlacionar.
        </div>
        <div v-else class="max-w-2xl overflow-hidden rounded-md border">
          <table class="w-full text-sm">
            <thead
              class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              <tr>
                <th class="px-3 py-2 font-semibold">Código</th>
                <th class="px-3 py-2 font-semibold">Preparo</th>
                <th class="px-3 py-2 text-right font-semibold">Rendimento</th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr
                v-for="row in blindMap.rows.value"
                :key="row.code"
                class="hover:bg-muted/30"
              >
                <td class="px-3 py-2">
                  <span
                    class="rounded-md border border-primary/30 bg-primary/5 px-2 py-0.5 font-mono text-sm font-bold tracking-wide text-primary"
                    >{{ row.code }}</span
                  >
                </td>
                <td class="px-3 py-2 font-medium">{{ row.name }}</td>
                <td class="px-3 py-2 text-right tabular-nums">
                  {{ row.output_quantity_display }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </main>
</template>
