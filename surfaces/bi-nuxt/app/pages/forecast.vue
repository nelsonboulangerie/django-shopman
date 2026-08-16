<script setup lang="ts">
// "O que esperar" — a única página do B.I. que olha para frente.
//
// A resposta nunca é um número solto: é o provável, a faixa onde caiu metade
// dos dias parecidos, e a lista do que sustenta isso. Quando a base não se
// sustenta, a página diz que não sabe — em vez de mostrar um número frágil sem
// aviso, que é como uma tela de previsão perde a confiança de quem a usa.
import type { DayForecast, ForecastOccasion } from "~/types/bi";
import {
  HORIZON_LABELS,
  basisHeadline,
  basisNotes,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  missingLabel,
  rangeLabel,
  shortDate,
  shortDateWithYear,
} from "~/presentation/bi";

const { report, pending, error, refresh, target, horizon } = useBiForecast();

const single = computed(() => (report.value?.horizon === "day" ? report.value.days[0] : null));

const openDays = computed(() =>
  (report.value?.days ?? []).filter((day: DayForecast) => !day.closed),
);

const chipClass = (active: boolean) =>
  active
    ? "bg-card font-semibold text-foreground shadow-sm"
    : "text-muted-foreground hover:bg-card/60 hover:text-foreground";

const periodSeries = (days: DayForecast[]) =>
  days.map((day) => ({
    label: `${day.weekday_label.slice(0, 3)} ${shortDate(day.date)}`,
    value: Number(day.revenue_q?.expected ?? 0),
    detail: day.closed
      ? `fechado${day.closed_reason ? ` · ${day.closed_reason}` : ""}`
      : day.revenue_q
        ? `${rangeLabel(day.revenue_q.low, day.revenue_q.high)} · ${formatInt(Math.round(day.orders?.expected ?? 0))} pedidos`
        : missingLabel(day.missing_reason),
  }));

const headline = (day: DayForecast) =>
  day.basis ? basisHeadline(day.basis, day.weekday_label) : "";

// "Dia das Mães (véspera)" em vez de tentar "Véspera do/da …": o artigo depende
// do gênero do nome, que vem do calendário e não é derivável da string.
const occasionTitle = (occasion: ForecastOccasion) =>
  `${occasion.name}${occasion.is_eve ? " (véspera)" : ""}`;
</script>

<template>
  <main class="flex flex-1 flex-col gap-4 p-4">
    <section class="flex flex-wrap items-end gap-3 rounded-md border border-border bg-card p-3">
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Dia que você está planejando
        <input
          v-model="target"
          type="date"
          class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
        />
      </label>
      <div
        class="flex items-center gap-0.5 rounded-md bg-muted p-1"
        role="group"
        aria-label="Horizonte da projeção"
      >
        <button
          v-for="option in HORIZON_LABELS"
          :key="option.key"
          type="button"
          class="inline-flex h-8 items-center rounded-md px-3 text-sm transition-all"
          :class="chipClass(horizon === option.key)"
          @click="horizon = option.key"
        >
          {{ option.label }}
        </button>
      </div>
      <p class="ml-auto max-w-md text-xs text-muted-foreground">
        A projeção compara com dias parecidos do passado. Ela não usa o período da barra acima, que
        serve para olhar o que já aconteceu.
      </p>
    </section>

    <p v-if="pending" class="text-sm text-muted-foreground">Carregando…</p>
    <div v-else-if="error" class="flex items-center gap-3">
      <p class="text-sm text-muted-foreground">Não deu para carregar os números.</p>
      <button
        type="button"
        class="h-9 rounded-md border border-border px-3 text-sm font-medium"
        @click="refresh()"
      >
        Tentar de novo
      </button>
    </div>

    <template v-else-if="report">
      <!-- Um dia: a pergunta da fornada -->
      <template v-if="single">
        <section
          v-if="single.closed"
          class="rounded-md border border-border bg-card p-4"
        >
          <h2 class="text-lg font-semibold text-foreground">
            {{ single.weekday_label }}, {{ shortDate(single.date) }}
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            A casa não abre neste dia{{ single.closed_reason ? ` (${single.closed_reason})` : "" }}.
          </p>
        </section>

        <!--
          Quando o dia TEM ocasião, ela lidera (decisão do dono).
          O padeiro que abre esta tela para planejar a véspera do dia das mães
          quer ver o número da véspera do dia das mães, não o de um sábado
          médio. O número genérico continua logo abaixo, porque é o contraponto
          que dá escala à ocasião: sem ele, "3,2× um dia normal" não diz nada.
        -->
        <section v-else-if="single.occasion" class="rounded-md border border-border bg-card p-4">
          <h2 class="text-lg font-semibold text-foreground">
            {{ occasionTitle(single.occasion) }}
          </h2>
          <p class="text-sm text-muted-foreground">
            {{ single.weekday_label }}, {{ shortDate(single.date) }}
          </p>

          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <StatTile
              label="Faturamento provável"
              :value="formatMoney(Math.round(single.occasion.expected_revenue_q))"
              :hint="`no ritmo das ${formatInt(single.occasion.years.length)} ocorrências anteriores, aplicado ao patamar de hoje`"
            />
            <StatTile
              v-if="single.revenue_q"
              :label="`Um ${single.weekday_label} comum`"
              :value="formatMoney(Math.round(single.revenue_q.expected))"
              hint="o contraponto: é o que a data acrescenta"
            />
          </div>

          <ul class="mt-3 space-y-1.5">
            <li
              v-for="year in single.occasion.years"
              :key="year.date"
              class="flex items-baseline justify-between gap-3 text-sm"
            >
              <span class="text-muted-foreground">{{ shortDateWithYear(year.date) }}</span>
              <span class="font-medium tabular-nums text-foreground">
                {{ formatMoney(year.revenue_q) }}
              </span>
              <span class="tabular-nums text-muted-foreground">
                {{ year.ratio.toFixed(1).replace(".", ",") }}× um dia normal
              </span>
            </li>
          </ul>
          <p class="mt-2 text-xs text-muted-foreground">
            Cada ocorrência medida contra o movimento típico da época dela.
            {{ formatInt(single.occasion.years.length) }}
            {{ single.occasion.years.length === 1 ? "ocorrência" : "ocorrências" }}: poucas para
            prever, o bastante para saber o que esperar.
          </p>

          <p v-if="single.basis" class="mt-3 text-sm text-foreground">{{ headline(single) }}</p>
          <ul v-if="single.basis" class="mt-1 space-y-0.5 text-xs text-muted-foreground">
            <li v-for="note in basisNotes(single.basis)" :key="note">{{ note }}</li>
          </ul>
          <p v-else class="mt-2 text-sm text-muted-foreground">
            {{ missingLabel(single.missing_reason) }}
          </p>
        </section>

        <section v-else class="rounded-md border border-border bg-card p-4">
          <h2 class="text-lg font-semibold text-foreground">
            {{ single.weekday_label }}, {{ shortDate(single.date) }}
          </h2>

          <template v-if="single.revenue_q && single.orders">
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              <StatTile
                label="Faturamento provável"
                :value="formatMoney(Math.round(single.revenue_q.expected))"
                :hint="`metade dos dias parecidos entre ${rangeLabel(single.revenue_q.low, single.revenue_q.high)}`"
              />
              <StatTile
                label="Pedidos prováveis"
                :value="formatInt(Math.round(single.orders.expected))"
                :hint="`entre ${formatInt(Math.round(single.orders.low))} e ${formatInt(Math.round(single.orders.high))}`"
              />
            </div>

            <p class="mt-3 text-sm text-foreground">{{ headline(single) }}</p>
            <ul class="mt-1 space-y-0.5 text-xs text-muted-foreground">
              <li v-for="note in basisNotes(single.basis!)" :key="note">{{ note }}</li>
            </ul>
          </template>

          <p v-else class="mt-2 text-sm text-muted-foreground">
            {{ missingLabel(single.missing_reason) }}
          </p>
        </section>

        <section
          v-if="single.branches.length"
          class="rounded-md border border-border bg-card p-3"
        >
          <h2 class="text-lg font-semibold text-foreground">E se o dia for diferente?</h2>
          <p class="mb-3 text-xs text-muted-foreground">
            Os mesmos dias parecidos, separados pelo que o tempo fez. Olhe pela janela e escolha o
            lado.
          </p>
          <div class="grid gap-3 sm:grid-cols-2">
            <div
              v-for="branch in single.branches"
              :key="branch.key"
              class="rounded-md border border-border p-3"
            >
              <p class="text-sm font-medium text-foreground">{{ branch.label }}</p>
              <p class="mt-1 text-xl font-semibold tabular-nums text-foreground">
                {{ formatMoneyCompact(Math.round(branch.revenue_q.expected)) }}
              </p>
              <p class="text-xs text-muted-foreground">
                {{ formatInt(Math.round(branch.orders.expected)) }} pedidos ·
                {{ formatInt(branch.sample_size) }} dias
              </p>
            </div>
          </div>
        </section>
      </template>

      <!-- Semana ou mês: a soma dos dias, cada um com a sua amostra -->
      <template v-else>
        <div class="grid grid-cols-2 gap-3">
          <StatTile
            label="Faturamento provável no período"
            :value="report.total_revenue_q ? formatMoney(Math.round(report.total_revenue_q.expected)) : '—'"
            :hint="
              report.total_revenue_q
                ? `entre ${rangeLabel(report.total_revenue_q.low, report.total_revenue_q.high)}`
                : 'um dia do período ficou sem base, então o total não sai'
            "
          />
          <StatTile
            label="Pedidos prováveis no período"
            :value="report.total_orders ? formatInt(Math.round(report.total_orders.expected)) : '—'"
            :hint="`${formatInt(openDays.length)} dias de expediente`"
          />
        </div>

        <p
          v-if="report.total_missing_days.length"
          class="rounded-md border border-border bg-card p-3 text-sm text-muted-foreground"
        >
          Sem total do período: não temos base para
          {{ report.total_missing_days.map(shortDate).join(", ") }}. Somar só os outros dias daria um
          número plausível e errado.
        </p>

        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Dia a dia</h2>
          <p class="mb-3 text-xs text-muted-foreground">
            Faturamento provável de cada dia; o tooltip traz a faixa e os pedidos
          </p>
          <ChartBarSeries
            :points="periodSeries(report.days)"
            :format="(v) => formatMoneyCompact(v)"
          />
        </section>
      </template>
    </template>
  </main>
</template>
