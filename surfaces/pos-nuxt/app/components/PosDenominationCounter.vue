<script setup lang="ts">
// Contador OPCIONAL por denominação: quantidade × cédula/moeda, com a soma ao
// vivo preenchendo o campo de valor de quem o abriu (abertura e fechamento).
//
// É AJUDA de contagem, não obrigação: o campo de valor continua sendo a
// resposta, e quem conta o maço de cabeça digita direto. O desenho das
// denominações é o mesmo do pedido de troco — cédula retangular e verde,
// moeda redonda e amarela — porque é assim que a mão reconhece no balcão.
//
// ⚠️ Nada aqui fala de esperado: o contador soma o que o operador DIZ que
// contou, e só. Sugerir quantidade a partir de turnos anteriores quebraria o
// regime de contagem cega.
import { denominationCountTotalQ, formatAmountInput } from "~/presentation/cash";
import type { POSChangeDenomination } from "~/types/pos";

const props = defineProps<{
  denominations: readonly POSChangeDenomination[];
  disabled?: boolean;
}>();

const emit = defineEmits<{ "total-q": [totalQ: number] }>();

// A quantidade digitada, por denominação (`q` em centavos). Começa vazia:
// contar de verdade, não confirmar um default.
const counts = reactive<Record<number, string>>({});
const totalQ = computed(() => denominationCountTotalQ(counts));
const totalDisplay = computed(() => formatAmountInput(totalQ.value));

// Emite só quando a soma MUDA — nunca no mount. Quem abriu o contador pode já
// ter digitado um valor no campo; sobrescrevê-lo com 0 antes do primeiro toque
// apagaria uma resposta dada.
watch(totalQ, (value) => emit("total-q", value));
</script>

<template>
  <div class="grid gap-2 rounded-md border bg-muted/30 p-3">
    <div
      v-for="denom in props.denominations"
      :key="denom.q"
      class="grid grid-cols-[auto_1fr_auto] items-center gap-3"
    >
      <span
        class="inline-flex items-center justify-center border text-sm font-semibold tabular-nums"
        :class="[
          denom.shape === 'note' ? 'h-10 w-16 rounded-md' : 'size-10 rounded-full',
          denom.shape === 'note'
            ? 'border-success/40 bg-success/10 text-success'
            : 'border-warning/40 bg-warning/10 text-amber-700 dark:text-amber-400',
        ]"
      >
        {{ denom.label }}
      </span>
      <label class="grid justify-items-end gap-0.5 text-sm">
        <span class="sr-only">{{ denom.shape === "note" ? "Notas" : "Moedas" }} de {{ denom.label }}</span>
        <UiInput
          v-model="counts[denom.q]"
          inputmode="numeric"
          pattern="[0-9]"
          placeholder="0"
          class="w-20 text-right tabular-nums"
          :disabled="props.disabled"
          :aria-label="`Quantidade de ${denom.shape === 'note' ? 'notas' : 'moedas'} de ${denom.label}`"
        />
      </label>
      <span class="w-20 text-right text-sm tabular-nums text-muted-foreground">
        {{ formatAmountInput(Number(denom.q) * (Number.parseInt(counts[denom.q] || "0", 10) || 0)) }}
      </span>
    </div>
    <p class="flex items-baseline justify-between border-t pt-2 text-sm">
      <span class="text-muted-foreground">Soma da contagem</span>
      <span class="font-medium tabular-nums">R$ {{ totalDisplay }}</span>
    </p>
  </div>
</template>
