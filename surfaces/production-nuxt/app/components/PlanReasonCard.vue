<script setup lang="ts">
// O "Por quê" de uma linha do Planejamento (SUITE-UX UX-P2): abre por cima da
// linha, ancorado nela, e carrega o que a linha deixou de mostrar. A conta
// (projeção + encomendas + margem = sugestão), o histórico curto, a falta de
// insumo com o atalho para o Compras e a alternativa que cabe no estoque. Cada
// bloco só aparece quando o backend tem o dado: nada é inventado aqui.
// O invólucro (popover, Esc, foco) é do UiPopover na grade; este componente é
// só o conteúdo, para ser testável sem o overlay.
import {
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
      <button
        type="button"
        class="-mr-2 -mt-1 grid size-12 shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
        aria-label="Fechar"
        @click="emit('close')"
      >
        <Icon name="lucide:x" class="size-4" />
      </button>
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
        <span>
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
      </li>
    </ul>

    <!-- A falta de insumo, antes de planejar: o que falta e onde pedir. -->
    <section
      v-if="suggestion.material_shortages.length"
      class="mx-4 flex flex-col gap-2 rounded-lg bg-warning/12 p-3"
      data-testid="reason-material"
      aria-label="Falta de insumo"
    >
      <ul class="flex flex-col gap-1 text-sm">
        <li
          v-for="item in suggestion.material_shortages"
          :key="item.sku"
          class="flex items-start gap-2 font-medium"
        >
          <Icon
            name="lucide:lock"
            class="mt-0.5 size-4 shrink-0 text-warning"
          />
          <span>{{ shortageLine(item) }}</span>
        </li>
      </ul>
      <a
        v-if="purchaseUrl"
        :href="purchaseUrl"
        v-bind="attrsFor(purchaseUrl)"
        class="inline-flex min-h-12 items-center gap-2 self-start rounded-md border bg-background px-3 text-sm font-medium transition hover:bg-accent"
      >
        Pedir no Compras
        <Icon name="lucide:external-link" class="size-4" />
      </a>
    </section>

    <footer class="flex flex-wrap items-center gap-2 px-4 pb-4">
      <UiButton
        v-if="alternative"
        type="button"
        variant="outline"
        class="min-h-12 border-primary text-primary hover:bg-primary/10 hover:text-primary"
        @click="emit('plan', alternative, 'manual')"
      >
        <Icon name="lucide:check" class="size-4" />
        Planejar {{ alternative }} (cabe no estoque)
      </UiButton>
      <UiButton
        v-else-if="canPlanSuggested"
        type="button"
        variant="outline"
        class="min-h-12 border-primary text-primary hover:bg-primary/10 hover:text-primary"
        @click="emit('plan', suggestion.quantity, 'suggested')"
      >
        <Icon name="lucide:check" class="size-4" />
        Planejar {{ suggestion.quantity }}
      </UiButton>
      <UiButton
        type="button"
        variant="ghost"
        class="ml-auto min-h-12"
        @click="emit('close')"
      >
        Fechar
      </UiButton>
    </footer>
  </div>
</template>
