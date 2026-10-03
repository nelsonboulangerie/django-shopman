<script setup lang="ts">
// Os recortes das Encomendas numa linha só, no tamanho de toque do balcão (44 px).
//
// - Os RECORTES DE TODO DIA são botões de um toque (decisão do dono, P1 de
//   02/10): A receber, Sem Via Pedido, Retiradas, Entregas, cada um com a
//   contagem do que mostraria com os outros recortes como estão. Apertado,
//   desliga. Escrevem o mesmo estado da URL de sempre.
// - O "Filtrar" (a `FilterBar` do kit) fica para o RESTO: Pagas e "Na conta da
//   casa". O que já tem botão não aparece de novo nem como opção nem como chip
//   (`presentation/preorders`, `barDimensions` e `toBarFilters`).
//
// À direita da mesma linha mora o que age sobre o visível (o slot `actions`:
// o lote das vias que faltam).
//
// Pagamento a conferir não é opção escondida: é aviso próprio, com o gesto de
// ver só elas. "Não sei" nunca some dentro de "a receber" ou de "pagas". Ligado
// o recorte, o aviso sai: o chip "Pagamento: A conferir" diz o que se vê, e o X
// dele (ou "Limpar filtros") é o único jeito de voltar.
import {
  barDimensions,
  checkCount,
  checkPaymentNotice,
  fromBarFilters,
  shortcutChips,
  toBarFilters,
  toggleShortcut,
  type PreorderFilters,
  type Shortcut,
} from "~/presentation/preorders";
import type { ActiveFilters } from "../../../operator-kit/app/types/filters";
import type { PreorderCard } from "~/types/preorders";

const props = defineProps<{ cards: readonly PreorderCard[] }>();
const filters = defineModel<PreorderFilters>({ required: true });

const shortcuts = computed(() => shortcutChips(props.cards, filters.value));
const dimensions = computed(() => barDimensions(props.cards, filters.value));
const active = computed<ActiveFilters>({
  get: () => toBarFilters(filters.value),
  set: (next) => { filters.value = fromBarFilters(filters.value, next); },
});
const notice = computed(() => checkPaymentNotice(checkCount(props.cards, filters.value)));

function press(shortcut: Shortcut) {
  filters.value = toggleShortcut(filters.value, shortcut);
}

function showOnlyCheck() {
  filters.value = { ...filters.value, pay: "check" };
}
</script>

<template>
  <div class="grid gap-2" data-preorders-filters>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div v-if="shortcuts.length" class="flex flex-wrap items-center gap-1.5" role="group" aria-label="Recortes de todo dia" data-preorders-shortcuts>
        <button
          v-for="chip in shortcuts"
          :key="`${chip.dimension}:${chip.value}`"
          type="button"
          class="inline-flex min-h-control items-center gap-2 rounded-full border px-3.5 text-sm font-medium transition focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          :class="chip.pressed
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-border bg-background text-foreground hover:bg-accent'"
          :aria-pressed="chip.pressed"
          :data-preorders-shortcut="`${chip.dimension}:${chip.value}`"
          @click="press(chip)"
        >
          {{ chip.label }}
          <span class="tabular-nums" :class="chip.pressed ? '' : 'text-muted-foreground'">{{ chip.count }}</span>
        </button>
      </div>
      <FilterBar
        v-if="dimensions.length"
        v-model="active"
        :dimensions="dimensions"
        label="Filtrar"
        touch
        class="min-w-0"
        role="group"
        aria-label="Filtrar encomendas"
      />
      <slot name="actions" />
    </div>
    <div
      v-if="notice && filters.pay !== 'check'"
      class="flex flex-wrap items-center gap-2 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning"
      data-preorders-check-notice
    >
      <Icon name="lucide:circle-help" class="size-4 shrink-0" />
      <!-- Na tela estreita a frase fica inteira e o botão desce, em vez de a frase
           virar uma coluna de uma palavra por linha. -->
      <span class="min-w-[min(100%,16rem)] flex-1">{{ notice }}</span>
      <UiButton
        variant="outline"
        data-preorders-check-only
        @click="showOnlyCheck"
      >
        Mostrar só essas
      </UiButton>
    </div>
  </div>
</template>
