<script setup lang="ts">
// O "Por quê" de uma linha do Planejamento (SUITE-UX UX-P2): abre por cima da
// linha, ancorado nela, e carrega o que a linha deixou de mostrar. A conta
// (projeção + encomendas + margem = sugestão), o histórico curto, a falta de
// insumo com o atalho para o Compras e a alternativa que cabe no estoque. Cada
// bloco só aparece quando o backend tem o dado: nada é inventado aqui.
// O invólucro (popover, Esc, foco) é do NuxtPopover na grade; este componente é
// só o conteúdo, para ser testável sem o overlay.
import {
  DAY_DOT_TONE,
  fittingAlternative,
  shortageLine,
  suggestionBasisLine,
  suggestionHistory,
  suggestionMath,
} from "~/presentation/planningReason";
import type { ProductionSuggestionProjection } from "~/types/production";

const props = defineProps<{
  suggestion: ProductionSuggestionProjection;
  productName: string;
  isoDate: string;
  purchaseUrl: string;
  canPlanSuggested: boolean;
  canPlanManual: boolean;
}>();

const emit = defineEmits<{
  plan: [quantity: string, source: "manual" | "suggested"];
  close: [];
}>();

const { attrsFor } = useOperatorAppLink();

const math = computed(() => suggestionMath(props.suggestion, props.isoDate));
const history = computed(() =>
  suggestionHistory(props.suggestion, props.isoDate),
);
const basisLine = computed(() =>
  suggestionBasisLine(props.suggestion, props.isoDate),
);
const alternative = computed(() =>
  props.canPlanManual ? fittingAlternative(props.suggestion) : null,
);
const HISTORY_ICON = {
  soldout: "lucide:clock-alert",
  leftover: "lucide:archive",
  season: "lucide:calendar-range",
  bi: "lucide:chart-column",
} as const;
const HISTORY_TONE = {
  soldout: "text-destructive",
  leftover: "text-warning",
  season: "text-muted-foreground",
  bi: "text-primary",
} as const;
</script>

<template>
  <div class="flex flex-col gap-3 text-left" data-testid="plan-reason">
    <header class="flex items-start gap-2 border-b border-border px-4 pb-3 pt-3.5">
      <div class="min-w-0 flex-1">
        <h2 class="op-title">
          Por que {{ suggestion.quantity }}
          <span class="font-normal text-muted-foreground"
            >· {{ productName }}</span
          >
        </h2>
        <p class="op-micro text-muted-foreground">{{ basisLine }}</p>
      </div>
      <OperatorKbd class="mt-1 hidden md:inline-flex">Esc</OperatorKbd>
      <NuxtButton
        icon="i-lucide-x"
        color="neutral"
        variant="ghost"
        square
        class="-mr-2 -mt-1 shrink-0"
        aria-label="Fechar"
        @click="emit('close')"
      />
    </header>

    <!-- A conta: os termos da fórmula, fechando no número da linha. -->
    <section class="px-4" aria-label="A conta da sugestão">
      <ol
        class="flex flex-wrap items-stretch gap-1.5"
        data-testid="reason-math"
      >
        <template v-for="(term, index) in math.terms" :key="term.label">
          <li
            v-if="index > 0"
            aria-hidden="true"
            class="self-center text-sm text-muted-foreground"
          >
            +
          </li>
          <li
            class="flex min-w-16 flex-1 flex-col items-center rounded-lg bg-muted px-2 py-1.5"
          >
            <span class="op-heading leading-[1.1] tnum">{{ term.value }}</span>
            <span class="op-micro text-muted-foreground">{{ term.label }}</span>
          </li>
        </template>
        <li
          aria-hidden="true"
          class="self-center text-sm text-muted-foreground"
        >
          =
        </li>
        <li
          class="flex min-w-16 flex-1 flex-col items-center rounded-lg bg-primary/12 px-2 py-1.5"
        >
          <span class="op-heading leading-[1.1] tnum text-primary">{{
            math.total.value
          }}</span>
          <span class="op-micro text-muted-foreground">{{
            math.total.label
          }}</span>
        </li>
      </ol>
      <p
        v-if="math.marginNote"
        class="mt-1 text-xs text-muted-foreground"
        data-testid="reason-margin-note"
      >
        Margem: {{ math.marginNote }}
      </p>
    </section>

    <!-- O histórico curto: o que a média sozinha não conta. -->
    <ul
      v-if="history.length"
      class="flex flex-col gap-1.5 px-4 text-sm"
      data-testid="reason-history"
    >
      <li
        v-for="(line, index) in history"
        :key="`${line.kind}:${index}`"
        class="flex items-start gap-2"
      >
        <Icon
          :name="HISTORY_ICON[line.kind]"
          :class="['mt-0.5 size-4 shrink-0', HISTORY_TONE[line.kind]]"
        />
        <span class="min-w-0 flex-1">
          <span
            :class="
              line.kind === 'soldout' ? 'font-medium text-destructive' : ''
            "
            >{{ line.text }}</span
          >
          <span v-if="line.note" class="block text-xs text-muted-foreground">{{
            line.note
          }}</span>
        </span>
        <!-- Um ponto por dia recente da amostra, com a data embaixo (v4 pino 3). -->
        <ol
          v-if="line.kind === 'soldout' && suggestion.recent_days?.length"
          class="flex shrink-0 gap-2.5"
          aria-label="Desfecho dos últimos dias"
          data-testid="reason-days"
        >
          <li
            v-for="day in suggestion.recent_days"
            :key="day.date"
            class="flex flex-col items-center gap-1"
            :title="
              day.outcome === 'soldout'
                ? `${day.date_display}: acabou${day.soldout_at ? ` às ${day.soldout_at}` : ''}`
                : day.outcome === 'leftover'
                  ? `${day.date_display}: sobrou`
                  : `${day.date_display}: vendeu o planejado`
            "
          >
            <span class="size-3 rounded-full" :class="DAY_DOT_TONE[day.outcome]" />
            <span class="op-micro tnum text-muted-foreground">{{ day.date_display }}</span>
          </li>
        </ol>
      </li>
    </ul>

    <!-- A falta de insumo, antes de planejar: o que falta e onde pedir. -->
    <NuxtAlert
      v-if="suggestion.material_shortages.length"
      color="warning"
      variant="subtle"
      icon="i-lucide-lock"
      class="mx-4 w-auto"
      data-testid="reason-material"
      aria-label="Falta de insumo"
    >
      <template #description>
        <ul class="flex flex-col gap-1 text-sm">
          <li
            v-for="item in suggestion.material_shortages"
            :key="item.sku"
            class="font-medium"
          >
            {{ shortageLine(item) }}
          </li>
        </ul>
      </template>
      <template v-if="purchaseUrl" #actions>
        <NuxtButton
          :href="purchaseUrl"
          v-bind="attrsFor(purchaseUrl)"
          color="warning"
          variant="outline"
          trailing-icon="i-lucide-external-link"
          label="Pedir no Compras"
        />
      </template>
    </NuxtAlert>

    <footer class="flex flex-wrap items-center gap-2 px-4 pb-4">
      <NuxtButton
        v-if="alternative"
        color="primary"
        variant="outline"
        icon="i-lucide-check"
        :label="`Planejar ${alternative} (cabe no estoque)`"
        @click="emit('plan', alternative, 'manual')"
      />
      <NuxtButton
        v-else-if="canPlanSuggested"
        color="primary"
        variant="outline"
        icon="i-lucide-check"
        :label="`Planejar ${suggestion.quantity}`"
        @click="emit('plan', suggestion.quantity, 'suggested')"
      />
      <NuxtButton
        color="neutral"
        variant="ghost"
        class="ml-auto"
        label="Fechar"
        @click="emit('close')"
      />
    </footer>
  </div>
</template>
