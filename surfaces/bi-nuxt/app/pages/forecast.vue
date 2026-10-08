<script setup lang="ts">
// "O que esperar?": a única página do B.I. que olha para frente.
//
// A resposta nunca é um número solto: é o provável, a faixa onde caiu metade
// dos dias parecidos, e a lista do que sustenta isso. Quando a base não se
// sustenta, a página diz que não sabe, em vez de mostrar um número frágil sem
// aviso, que é como uma tela de previsão perde a confiança de quem a usa.
//
// Peças do kit (PR-B7 do WP-BI-CANON-LAUDO): quadro (`OperatorReadingCard`, com o
// ⋯ "Exportar CSV deste quadro"), métrica (`OperatorMetric`; dentro de um quadro,
// `soft`), gráfico (`OperatorReadingChart`), frescor (`ReadFreshness`), período
// compacto e o ⋯ da página (`OperatorReadingPageMenu`). Tabela é `NuxtTable`;
// vazio e carregando, `NuxtEmpty`.
import type { DayForecast } from "~/types/bi";
import { readingMoneyFormat } from "../../../operator-kit/app/presentation/readingChart";
import {
  basisHeadline,
  basisNotes,
  cashOrdersNote,
  changeHabitNotes,
  changeMixCaveat,
  coinFloorHint,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  missingLabel,
  rangeLabel,
  shortDate,
} from "~/presentation/bi";
import {
  FORECAST_SERIES,
  forecastChartPoints,
  forecastDayRows,
  forecastDaysCsv,
  missingDaysLabel,
  occasionTitle,
  occasionYearRows,
  occasionYearsCsv,
  ordinaryWeekdayLabel,
} from "~/presentation/forecast";

const { report, freshness, pending, error, refresh, target, horizon, period, presets } = useBiForecast();
const shareItems = useBiShareMenuItems();

// O troco é a mesma decisão de véspera: quem planeja o sábado quer abastecer a
// gaveta no mesmo momento em que decide a fornada. Separá-lo em outra aba faria
// a conta existir e ninguém olhar.
const { change } = useBiChange(target, horizon);

const singleChange = computed(() =>
  change.value?.horizon === "day" ? change.value.days[0] : null,
);

const days = computed(() => report.value?.days ?? []);
const single = computed(() => (report.value?.horizon === "day" ? days.value[0] : null));

const openDays = computed(() => days.value.filter((day: DayForecast) => !day.closed));

const dayTitle = (day: DayForecast) => `${day.weekday_label}, ${shortDate(day.date)}`;

const headline = (day: DayForecast) =>
  day.basis ? basisHeadline(day.basis, day.weekday_label) : "";

const retryActions = computed(() => [
  {
    label: "Tentar de novo",
    icon: "i-lucide-refresh-cw",
    color: "error" as const,
    variant: "outline" as const,
    onClick: () => void refresh(),
  },
]);

const yearColumns = [
  { accessorKey: "label", header: "Ocorrência" },
  { accessorKey: "revenue", header: "Faturamento", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { accessorKey: "ratio", header: "Contra um dia normal", meta: { class: { th: "text-right", td: "text-right tnum" } } },
];

const dayColumns = [
  { accessorKey: "label", header: "Dia" },
  { accessorKey: "revenue", header: "Faturamento provável", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  // No celular a faixa e os pedidos saem da tabela (seguem no ponto do gráfico e no
  // CSV): o dia, o provável e o porquê de cada dia sem número cabem sem rolar.
  { accessorKey: "range", header: "Faixa", meta: { class: { th: "max-sm:hidden", td: "tnum max-sm:hidden" } } },
  { accessorKey: "orders", header: "Pedidos prováveis", meta: { class: { th: "text-right max-sm:hidden", td: "text-right tnum max-sm:hidden" } } },
  { accessorKey: "note", header: "Observação", meta: { class: { td: "whitespace-normal text-muted sm:min-w-48" } } },
];

const chartPoints = computed(() => forecastChartPoints(days.value));
const dayRows = computed(() => forecastDayRows(days.value));
const daysCsv = computed(() => forecastDaysCsv(days.value));
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <!--
      O período mora na linha de recortes, como no Histórico do Gestor, com o frescor
      da leitura no fim da linha. No cabeçalho ele empurrava o título para fora da tela
      no tablet.
    -->
    <OperatorPageHeader title="O que esperar?">
      <template #actions>
        <OperatorReadingPageMenu :items="shareItems" />
      </template>
      <template #filters>
        <OperatorPeriodPicker
          v-model="period"
          :presets="presets"
          compact
          align="start"
          label="Período que você está planejando"
        />
        <ClientOnly>
          <ReadFreshness inline class="ms-auto" :metadata="freshness" :failed="Boolean(error)" />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <p class="text-xs text-muted">
        A projeção compara com dias parecidos do passado. O período, aqui, é o que você está planejando;
        as outras telas do B.I. olham o que já aconteceu.
      </p>
      <NuxtEmpty
        v-if="pending && !report"
        loading
        title="Carregando a projeção"
        description="Procurando os dias parecidos no histórico."
        data-bi-loading
      />
      <NuxtAlert
        v-else-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        title="Não deu para carregar a projeção."
        :actions="retryActions"
        orientation="horizontal"
        role="alert"
        data-bi-error
      />

      <template v-if="report">
        <NuxtEmpty
          v-if="!days.length"
          icon="i-lucide-calendar-search"
          title="Sem projeção para este período"
          description="O servidor não devolveu nenhum dia. Escolha outro período no cabeçalho."
          data-bi-forecast-empty
        />

        <!-- Um dia: a pergunta da fornada -->
        <template v-else-if="single">
          <NuxtEmpty
            v-if="single.closed"
            icon="i-lucide-store"
            :title="`A casa não abre neste dia${single.closed_reason ? ` (${single.closed_reason})` : ''}`"
            :description="`${dayTitle(single)}: não há o que projetar.`"
            data-bi-forecast-closed
          />

          <!--
            Quando o dia TEM ocasião, ela lidera (decisão do dono).
            O padeiro que abre esta tela para planejar a véspera do dia das mães
            quer ver o número da véspera do dia das mães, não o de um sábado
            médio. O número genérico continua ao lado, porque é o contraponto
            que dá escala à ocasião: sem ele, "3,2× um dia normal" não diz nada.
          -->
          <OperatorReadingCard
            v-else-if="single.occasion"
            :title="occasionTitle(single.occasion)"
            :description="dayTitle(single)"
            :csv="occasionYearsCsv(single.occasion.years)"
          >
            <div class="grid gap-3 sm:grid-cols-2">
              <OperatorMetric
                variant="soft"
                title="Faturamento provável"
                :value="formatMoney(Math.round(single.occasion.expected_revenue_q))"
                :hint="`No ritmo ${single.occasion.years.length === 1 ? 'da ocorrência anterior' : `das ${formatInt(single.occasion.years.length)} ocorrências anteriores`}, aplicado ao patamar de hoje.`"
              />
              <OperatorMetric
                v-if="single.revenue_q"
                variant="soft"
                :title="ordinaryWeekdayLabel(single.weekday_label)"
                :value="formatMoney(Math.round(single.revenue_q.expected))"
                hint="O contraponto: a diferença é o que a data acrescenta."
              />
            </div>

            <NuxtTable
              class="mt-3"
              :data="occasionYearRows(single.occasion.years)"
              :columns="yearColumns"
              :caption="`Ocorrências anteriores de ${occasionTitle(single.occasion)}`"
              data-bi-forecast-occasion-years
            />
            <p class="mt-2 text-xs text-muted">
              Cada ocorrência medida contra o movimento típico da época dela.
              {{ formatInt(single.occasion.years.length) }}
              {{ single.occasion.years.length === 1 ? "ocorrência" : "ocorrências" }}: poucas para
              prever, o bastante para saber o que esperar.
            </p>

            <template v-if="single.basis">
              <p class="mt-3 text-sm text-highlighted">{{ headline(single) }}</p>
              <ul class="mt-1 space-y-0.5 text-xs text-muted">
                <li v-for="note in basisNotes(single.basis)" :key="note">{{ note }}</li>
              </ul>
            </template>
            <p v-else class="mt-3 text-sm text-muted">{{ missingLabel(single.missing_reason) }}</p>
          </OperatorReadingCard>

          <OperatorReadingCard v-else :title="dayTitle(single)">
            <template v-if="single.revenue_q && single.orders && single.basis">
              <div class="grid gap-3 sm:grid-cols-2">
                <OperatorMetric
                  variant="soft"
                  title="Faturamento provável"
                  :value="formatMoney(Math.round(single.revenue_q.expected))"
                  :hint="`Metade dos dias parecidos ficou entre ${rangeLabel(single.revenue_q.low, single.revenue_q.high)}.`"
                />
                <OperatorMetric
                  variant="soft"
                  title="Pedidos prováveis"
                  :value="formatInt(Math.round(single.orders.expected))"
                  :hint="`Entre ${formatInt(Math.round(single.orders.low))} e ${formatInt(Math.round(single.orders.high))}.`"
                />
              </div>

              <p class="mt-3 text-sm text-highlighted">{{ headline(single) }}</p>
              <ul class="mt-1 space-y-0.5 text-xs text-muted">
                <li v-for="note in basisNotes(single.basis)" :key="note">{{ note }}</li>
              </ul>
            </template>

            <NuxtEmpty
              v-else
              variant="naked"
              icon="i-lucide-chart-no-axes-column"
              title="Sem projeção para este dia"
              :description="missingLabel(single.missing_reason)"
            />
          </OperatorReadingCard>

          <OperatorReadingCard
            v-if="!single.closed && single.branches.length"
            title="E se o dia for diferente?"
            description="Os mesmos dias parecidos, separados pelo que o tempo fez. Olhe pela janela e escolha o lado."
          >
            <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <OperatorMetric
                v-for="branch in single.branches"
                :key="branch.key"
                variant="soft"
                :title="branch.label"
                :value="formatMoneyCompact(Math.round(branch.revenue_q.expected))"
                :hint="`${formatInt(Math.round(branch.orders.expected))} pedidos · ${formatInt(branch.sample_size)} dias`"
                :data-bi-forecast-branch="branch.key"
              />
            </div>
          </OperatorReadingCard>

          <!--
            Troco: irmã da projeção, e no mesmo lugar de propósito. Quem abre esta
            tela para planejar o sábado decide a fornada e o caixa na mesma
            sentada; o troco numa aba própria seria uma conta que existe e ninguém
            olha, e a falta continuaria aparecendo no meio da fila.
          -->
          <OperatorReadingCard
            v-if="singleChange && !singleChange.closed"
            title="Troco para separar"
            description="Para abastecer na véspera, no seu tempo, em vez de resolver no meio do movimento."
          >
            <template v-if="singleChange.change_q && singleChange.cash_orders && change?.habit">
              <div class="grid gap-3 sm:grid-cols-2">
                <OperatorMetric
                  variant="soft"
                  title="Troco provável"
                  :value="formatMoney(Math.round(singleChange.change_q.expected))"
                  :hint="`Entre ${rangeLabel(singleChange.change_q.low, singleChange.change_q.high)}.`"
                />
                <OperatorMetric
                  v-if="change.mix && singleChange.coin_floor_q !== null"
                  variant="soft"
                  title="Em moeda, no mínimo"
                  :value="formatMoney(Math.round(singleChange.coin_floor_q))"
                  :hint="coinFloorHint(change.mix)"
                />
              </div>

              <p v-if="change.mix" class="mt-2 text-xs text-muted">
                {{ changeMixCaveat(change.mix) }}
              </p>

              <p class="mt-3 text-sm text-highlighted">
                {{
                  cashOrdersNote(
                    singleChange.cash_orders.expected,
                    singleChange.cash_share_percent,
                    singleChange.cash_share_days,
                  )
                }}
              </p>
              <ul class="mt-1 space-y-0.5 text-xs text-muted">
                <li v-for="note in changeHabitNotes(change.habit)" :key="note">{{ note }}</li>
              </ul>
            </template>

            <NuxtEmpty
              v-else
              variant="naked"
              icon="i-lucide-coins"
              title="Sem previsão de troco"
              :description="missingLabel(singleChange.missing_reason)"
            />
          </OperatorReadingCard>
        </template>

        <!-- Semana ou mês: a soma dos dias, cada um com a sua amostra -->
        <template v-else>
          <div class="grid gap-3 sm:grid-cols-3">
            <OperatorMetric
              title="Faturamento provável no período"
              :value="report.total_revenue_q ? formatMoney(Math.round(report.total_revenue_q.expected)) : 'sem dado'"
              :hint="
                report.total_revenue_q
                  ? `Entre ${rangeLabel(report.total_revenue_q.low, report.total_revenue_q.high)}.`
                  : 'Um dia do período ficou sem base, então o total não sai.'
              "
            />
            <OperatorMetric
              title="Pedidos prováveis no período"
              :value="report.total_orders ? formatInt(Math.round(report.total_orders.expected)) : 'sem dado'"
              :hint="`${formatInt(openDays.length)} ${openDays.length === 1 ? 'dia' : 'dias'} de expediente.`"
            />
            <OperatorMetric
              title="Troco no período"
              :value="change?.total_change_q ? formatMoney(Math.round(change.total_change_q.expected)) : 'sem dado'"
              :hint="
                change?.total_change_q
                  ? `Entre ${rangeLabel(change.total_change_q.low, change.total_change_q.high)}.`
                  : change?.missing_reason
                    ? missingLabel(change.missing_reason)
                    : 'Um dia do período ficou sem base, então o total não sai.'
              "
            />
          </div>

          <NuxtAlert
            v-if="report.total_missing_days.length"
            color="info"
            variant="subtle"
            icon="i-lucide-info"
            title="Sem total do período"
            :description="`Não temos base para ${missingDaysLabel(report.total_missing_days)}. Somar só os outros dias daria um número plausível e errado.`"
            data-bi-forecast-missing
          />

          <OperatorReadingCard
            title="Dia a dia"
            description="O faturamento provável de cada dia e a faixa onde caiu metade dos dias parecidos."
            :csv="daysCsv"
          >
            <OperatorReadingChart
              title="Faturamento provável por dia"
              kind="line"
              axis-label="Dia"
              :series="FORECAST_SERIES"
              :points="chartPoints"
              :format="readingMoneyFormat"
              empty-title="Sem dias para projetar"
            />
            <NuxtTable
              class="mt-3"
              :data="dayRows"
              :columns="dayColumns"
              caption="Projeção de cada dia do período"
              data-bi-forecast-days
            />
          </OperatorReadingCard>
        </template>
      </template>
    </main>
  </div>
</template>
