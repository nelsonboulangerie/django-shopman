<script setup lang="ts">
// As três peças de leitura do PR-K2 (WP-BI-CANON-LAUDO), com dados fixos: a métrica,
// o frescor da leitura e o período compacto (com o modo "um dia com ‹ ›"). É a
// vitrine de quem vai montar o B.I., a Central, o Marketing e o Compras.
import { ref } from "vue";

import type { PeriodSelection } from "../presentation/dates";
import type { MetricDelta } from "../presentation/metric";

const TODAY = "2026-10-06";
const READ_AT = "2026-10-06T15:36:22-03:00";

const drop: MetricDelta = {
  text: "queda de 23% vs período anterior (3.384)",
  tone: "negative",
  percent: "23%",
  direction: "down",
  caption: "vs período anterior (3.384)",
};
const rise: MetricDelta = {
  text: "alta de 8% vs período anterior (R$ 29,70)",
  tone: "positive",
  percent: "8%",
  direction: "up",
  caption: "vs período anterior (R$ 29,70)",
};
const noBase: MetricDelta = {
  text: "sem período anterior para comparar",
  tone: "neutral",
  percent: "",
  direction: "none",
  caption: "sem período anterior para comparar",
};

const period = ref<PeriodSelection>({ preset: "28d", from: "", to: "" });

// "Um dia com ‹ ›": o domingo é dia fechado, então a seta salta de segunda para
// sábado. A leitura só existe até ontem; a seta para frente para no último dia.
const OPEN_DAYS = ["2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-05"];
const day = ref<PeriodSelection>({ preset: "day", from: "2026-10-05", to: "" });
// "Voltar para hoje" deixa a âncora vazia; com o teto em ontem, o dia mostrado é o último.
const dayIndex = () => OPEN_DAYS.indexOf(day.value.from || OPEN_DAYS.at(-1)!);
const prevDay = () => OPEN_DAYS[dayIndex() - 1] ?? "";
const nextDay = () => OPEN_DAYS[dayIndex() + 1] ?? "";
</script>

<template>
  <section
    id="reading-pieces"
    class="space-y-4"
    aria-labelledby="reading-pieces-title"
    data-operator-audit-id="catalog-reading"
  >
    <div>
      <h2 id="reading-pieces-title" class="op-title">Peças de leitura</h2>
      <p class="op-body text-muted">
        Métrica, frescor da leitura e período compacto. Dados fixos de 6 de
        outubro.
      </p>
    </div>

    <NuxtCard
      title="Métrica"
      description="OperatorMetric: a figura vem formatada e o delta vem pronto da presentation."
    >
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <OperatorMetric
          title="Pedidos"
          description="Todos os canais"
          value="2.606"
          unit="pedidos"
          icon="i-lucide-receipt"
          :delta="drop"
        />
        <OperatorMetric
          title="Ticket médio"
          description="Vendas confirmadas"
          value="R$ 32,10"
          :delta="rise"
        />
        <OperatorMetric
          title="Faltou"
          description="Produtos que acabaram antes da hora"
          value="3"
          unit="produtos"
          tone="error"
          :delta="noBase"
          hint="Pão de queijo acabou às 10h40."
        />
        <OperatorMetric
          title="A resposta"
          value="Faltou pão de queijo em 3 dos 7 dias."
          size="statement"
        />
      </div>
    </NuxtCard>

    <div class="grid items-start gap-3 lg:grid-cols-2">
      <NuxtCard
        title="Frescor da leitura"
        description="ReadFreshness: a leitura sem tempo real diz quando foi gerada, em vez de um selo de ao vivo."
      >
        <div class="space-y-3">
          <ReadFreshness :metadata="{ generated_at: READ_AT }" />
          <ReadFreshness
            :metadata="{ generated_at: READ_AT }"
            failed
            realtime-label="Atualização automática"
          />
          <ReadFreshness :metadata="null" />
        </div>
      </NuxtCard>

      <NuxtCard
        title="Período compacto"
        description="OperatorPeriodPicker com compact: no celular o botão diz a forma curta. O nome acessível segue inteiro."
      >
        <div class="space-y-4">
          <OperatorPeriodPicker
            v-model="period"
            :presets="['day', 'week', 'month', '7d', '28d', '3m', 'max']"
            custom
            compact
            :today="TODAY"
            :max="TODAY"
            epoch="2024-01-01"
            label="Período de análise"
            align="start"
          />
          <div>
            <p class="op-label mb-2">Um dia com ‹ ›</p>
            <OperatorPeriodPicker
              v-model="day"
              compact
              :today="TODAY"
              max="2026-10-05"
              :prev-day="prevDay()"
              :next-day="nextDay()"
              label="Dia da leitura"
              align="start"
            />
            <p class="op-micro mt-2 text-muted">
              O domingo, 4 de outubro, é dia fechado: a seta salta de segunda
              para sábado. Hoje ainda não tem leitura.
            </p>
          </div>
        </div>
      </NuxtCard>
    </div>
  </section>
</template>
