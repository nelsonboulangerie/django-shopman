<script setup lang="ts">
// Métrica: UM valor que responde a uma pergunta, com o contexto que o torna legível.
//
// É a receita do Kitchen Sink virada peça (PR-K2 do WP-BI-CANON-LAUDO): `NuxtCard`
// com `title`/`description` (a anatomia do Card, nunca rótulo escrito à mão), a
// figura e, embaixo, a comparação num `NuxtBadge` no tom do melhorou/piorou com o
// "contra o quê" ao lado. Cobre o que o B.I. fazia com `StatTile` (número, unidade,
// veredito, delta, dica) e `BiAnswer` (a resposta em uma frase, `size="statement"`).
//
// A peça não calcula: a figura vem formatada e o delta vem pronto da presentation
// (`MetricDelta`). Sem base de comparação, a presentation manda `percent` vazio e a
// legenda diz que não há com o que comparar; a pílula some, a frase fica.
import {
  METRIC_DELTA_COLOR,
  METRIC_DELTA_ICON,
  METRIC_SIZE_CLASS,
  METRIC_TONE_CLASS,
  type MetricDelta,
  type MetricSize,
  type MetricTone,
} from "../presentation/metric";

withDefaults(
  defineProps<{
    /** A pergunta ou o nome do que se conta ("Faturamento", "A resposta"). */
    title: string;
    /** O recorte do número ("Vendas confirmadas", "Todos os canais"). */
    description?: string;
    /** A figura já formatada ("R$ 8.420,00", "24"), ou a frase no `statement`. */
    value: string;
    /** O que o número conta, na mesma linha ("produtos", "un."). */
    unit?: string;
    /** Tom da figura quando ela É um veredito. */
    tone?: MetricTone;
    delta?: MetricDelta;
    /** Uma linha de contexto depois da comparação. */
    hint?: string;
    /** Ícone do título: o cartão diz o que conta antes do número. */
    icon?: string;
    size?: MetricSize;
  }>(),
  {
    description: undefined,
    unit: "",
    tone: undefined,
    delta: undefined,
    hint: "",
    icon: "",
    size: "figure",
  },
);
</script>

<template>
  <NuxtCard :title="title" :description="description" data-operator-metric>
    <template v-if="icon" #title>
      <span class="flex items-center gap-1.5">
        <NuxtIcon :name="icon" class="size-4 shrink-0" aria-hidden="true" />{{
          title
        }}
      </span>
    </template>
    <!-- O espaço entre a figura e a unidade é texto, não só margem: o leitor de
         tela diz "2.606 pedidos", não "2.606pedidos". -->
    <p
      class="flex flex-wrap items-baseline gap-x-1.5 text-highlighted"
      :class="METRIC_SIZE_CLASS[size]"
      data-metric-value
    >
      <span :class="tone ? METRIC_TONE_CLASS[tone] : ''">{{ value }}</span
      ><template v-if="unit"
        >{{ " " }}<span class="op-label font-normal text-muted">{{
          unit
        }}</span></template
      >
    </p>
    <p
      v-if="delta"
      class="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 op-micro tnum"
      data-metric-delta
    >
      <span class="sr-only">{{ delta.text }}</span>
      <NuxtBadge
        v-if="delta.percent"
        :color="METRIC_DELTA_COLOR[delta.tone]"
        :icon="METRIC_DELTA_ICON[delta.direction]"
        :label="delta.percent"
        aria-hidden="true"
      />
      <span class="text-muted" aria-hidden="true">{{ delta.caption }}</span>
    </p>
    <p v-if="hint" class="mt-1 op-micro text-muted">{{ hint }}</p>
  </NuxtCard>
</template>
