<script setup lang="ts">
// Contador OPCIONAL por denominação: quantidade × cédula/moeda, com a soma ao
// vivo preenchendo o campo de valor de quem o abriu (abertura e fechamento).
//
// É AJUDA de contagem, não obrigação: o campo de valor continua sendo a
// resposta, e quem conta o maço de cabeça digita direto. O desenho das
// denominações é o mesmo do pedido de troco — cédula retangular e verde,
// moeda redonda e amarela — porque é assim que a mão reconhece no balcão.
//
// `layout="corridor"` (v4 `fim-do-dia.jpg` a, passo 1 do Fim do dia): o MESMO
// contador desenhado para o tablet em pé: cédulas e moedas em duas colunas, uma
// linha ativa por vez, "Contado até agora" e o numérico da tela com Anterior,
// Próxima, Limpar, +1 e Observação. `mode="total"` é o "Só o total": um campo só,
// escrito pelo mesmo numérico.
//
// ⚠️ Nada aqui fala de esperado: o contador soma o que o operador DIZ que
// contou, e só. Sugerir quantidade a partir de turnos anteriores quebraria o
// regime de contagem cega.
import { denominationCountTotalQ, formatAmountInput } from "~/presentation/cash";
import type { POSChangeDenomination } from "~/types/pos";

const props = defineProps<{
  denominations: readonly POSChangeDenomination[];
  disabled?: boolean;
  layout?: "list" | "corridor";
  /** Só no corredor: "denominations" (Por cédula) ou "total" (Só o total). */
  mode?: "denominations" | "total";
}>();

const emit = defineEmits<{
  "total-q": [totalQ: number];
  /** Corredor: quantas linhas já têm número, de quantas. */
  progress: [filled: number, total: number];
  /** Corredor: o operador pediu a observação. */
  note: [];
}>();

// A quantidade digitada, por denominação (`q` em centavos). Começa vazia:
// contar de verdade, não confirmar um default.
const counts = reactive<Record<number, string>>({});
const totalOnlyQ = ref(0);
const totalOnlyTouched = ref(false);
const countedQ = computed(() => denominationCountTotalQ(counts));
const totalQ = computed(() => (props.layout === "corridor" && props.mode === "total" ? totalOnlyQ.value : countedQ.value));
const totalDisplay = computed(() => formatAmountInput(totalQ.value));
const filled = computed(() => props.denominations.filter((d) => /^\d+$/.test(String(counts[d.q] ?? "").trim())).length);

// Emite só quando a soma MUDA — nunca no mount. Quem abriu o contador pode já
// ter digitado um valor no campo; sobrescrevê-lo com 0 antes do primeiro toque
// apagaria uma resposta dada.
watch(totalQ, (value) => emit("total-q", value));
watch(filled, (value) => emit("progress", value, props.denominations.length));

// ── Corredor ──────────────────────────────────────────────────────────────────
const notes = computed(() => props.denominations.filter((d) => d.shape === "note"));
const coins = computed(() => props.denominations.filter((d) => d.shape !== "note"));
const ordered = computed(() => [...notes.value, ...coins.value]);
const activeQ = ref<number | null>(null);
watch(ordered, (list) => {
  if (activeQ.value === null || !list.some((d) => d.q === activeQ.value)) activeQ.value = list[0]?.q ?? null;
}, { immediate: true });
const inputs = ref<Record<number, HTMLInputElement | null>>({});
function setActive(q: number) {
  activeQ.value = q;
}
function step(delta: number) {
  const list = ordered.value;
  const index = list.findIndex((d) => d.q === activeQ.value);
  const next = list[Math.max(0, Math.min(list.length - 1, index + delta))];
  if (next) activeQ.value = next.q;
}
function digit(value: string) {
  if (props.disabled) return;
  if (props.mode === "total") {
    totalOnlyTouched.value = true;
    totalOnlyQ.value = Math.min(99_999_999, totalOnlyQ.value * 10 + Number(value));
    return;
  }
  if (activeQ.value === null) return;
  const current = String(counts[activeQ.value] ?? "");
  counts[activeQ.value] = (current === "0" ? "" : current).concat(value).slice(0, 4);
}
function backspace() {
  if (props.disabled) return;
  if (props.mode === "total") {
    totalOnlyQ.value = Math.floor(totalOnlyQ.value / 10);
    return;
  }
  if (activeQ.value === null) return;
  counts[activeQ.value] = String(counts[activeQ.value] ?? "").slice(0, -1);
}
function clear() {
  if (props.mode === "total") {
    totalOnlyQ.value = 0;
    totalOnlyTouched.value = false;
    return;
  }
  if (activeQ.value !== null) counts[activeQ.value] = "";
}
function plusOne() {
  if (props.disabled || props.mode === "total" || activeQ.value === null) return;
  const n = Number.parseInt(String(counts[activeQ.value] ?? "0"), 10) || 0;
  counts[activeQ.value] = String(n + 1);
}
function onInput(q: number, raw: string) {
  counts[q] = String(raw || "").replace(/\D/g, "").slice(0, 4);
}
function subtotal(q: number): string {
  const n = Number.parseInt(String(counts[q] ?? ""), 10);
  return Number.isFinite(n) && n > 0 ? formatAmountInput(q * n) : "";
}
function denomLabel(d: POSChangeDenomination): string {
  return `R$ ${d.label}`;
}
defineExpose({ filled, totalQ, touched: computed(() => (props.mode === "total" ? totalOnlyTouched.value : filled.value > 0)) });
</script>

<template>
  <div v-if="layout !== 'corridor'" class="grid gap-2 rounded-md border bg-muted/30 p-3">
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
            : 'border-warning/40 bg-warning/10 text-warning',
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
          class="h-8 w-20 text-right tabular-nums"
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

  <!-- CORREDOR (v4 fim-do-dia a) -->
  <div v-else class="grid gap-4" data-drawer-count>
    <div v-if="mode !== 'total'" class="grid gap-x-6 gap-y-4 sm:grid-cols-2">
      <div v-for="column in [{ key: 'notes', title: 'Cédulas', list: notes }, { key: 'coins', title: 'Moedas', list: coins }]" :key="column.key" class="grid content-start gap-1.5">
        <p class="op-eyebrow text-muted-foreground">{{ column.title }}</p>
        <div
          v-for="denom in column.list"
          :key="denom.q"
          class="grid grid-cols-[4.5rem_1fr_4.5rem] items-center gap-3 rounded-lg px-2 py-1 transition"
          :class="activeQ === denom.q ? 'bg-secondary' : ''"
          :data-drawer-denom="denom.q"
          @click="setActive(denom.q)"
        >
          <span class="op-label font-semibold tnum">{{ denomLabel(denom) }}</span>
          <input
            :ref="(el) => { inputs[denom.q] = el as HTMLInputElement | null; }"
            :value="counts[denom.q] ?? ''"
            inputmode="numeric"
            class="h-8 w-full rounded-md border bg-card text-center text-base font-semibold tnum outline-none transition"
            :class="activeQ === denom.q ? 'border-2 border-foreground/80' : 'border-border'"
            :disabled="disabled"
            :aria-label="`Quantidade de ${denom.shape === 'note' ? 'notas' : 'moedas'} de ${denom.label}`"
            @focus="setActive(denom.q)"
            @input="onInput(denom.q, ($event.target as HTMLInputElement).value)"
            @keydown.enter.prevent="step(1)"
          />
          <span class="text-right op-micro text-muted-foreground tnum" :class="activeQ === denom.q ? 'font-semibold text-foreground' : ''">{{ subtotal(denom.q) }}</span>
        </div>
        <div v-if="column.key === 'coins'" class="mt-2 grid gap-0.5 rounded-lg border border-border bg-card p-3" data-drawer-counted>
          <span class="op-micro text-muted-foreground">Contado até agora</span>
          <strong class="text-3xl font-semibold tnum">R$ {{ totalDisplay }}</strong>
          <span class="op-micro text-muted-foreground tnum">{{ filled }} de {{ denominations.length }} valores contados</span>
        </div>
      </div>
    </div>
    <div v-else class="grid justify-items-center gap-1 rounded-lg border border-border bg-card p-5" data-drawer-total>
      <span class="op-label text-muted-foreground">Total da gaveta</span>
      <strong class="text-4xl font-semibold tnum">R$ {{ totalDisplay }}</strong>
    </div>

    <div class="grid grid-cols-4 gap-2" data-drawer-numpad>
      <template v-for="(row, rowIndex) in [[1, 2, 3], [4, 5, 6], [7, 8, 9], ['plus', 0, 'back']]" :key="rowIndex">
        <NuxtButton
          v-for="key in row"
          :key="String(key)"
          size="xl"
          color="neutral"
          variant="ghost"
          class="h-16 rounded-lg border text-3xl font-medium tnum transition hover:bg-muted active:bg-muted disabled:opacity-40 justify-center"
          :class="key === 'plus' ? 'border-transparent bg-secondary text-base font-semibold' : 'border-border bg-card'"
          :disabled="disabled || (key === 'plus' && mode === 'total')"
          :aria-label="typeof key === 'number' ? `Dígito ${key}` : key === 'back' ? 'Apagar último dígito' : 'Mais um'"
          @click="typeof key === 'number' ? digit(String(key)) : key === 'back' ? backspace() : plusOne()"
        >
          <Icon v-if="key === 'back'" name="lucide:delete" class="mx-auto size-6" />
          <template v-else>{{ key === "plus" ? "+1" : key }}</template>
        </NuxtButton>
        <NuxtButton
          v-if="rowIndex === 0"
          size="xl"
          color="neutral"
          variant="ghost"
          class="inline-flex h-16 items-center justify-center gap-1.5 rounded-lg bg-secondary op-label font-semibold transition disabled:opacity-40"
          :disabled="disabled || mode === 'total'"
          @click="step(-1)"
        ><Icon name="lucide:arrow-up" class="size-4" />Anterior</NuxtButton>
        <NuxtButton
          v-else-if="rowIndex === 1"
          size="xl"
          color="neutral"
          variant="ghost"
          class="inline-flex h-16 items-center justify-center gap-1.5 rounded-lg bg-secondary op-label font-semibold transition disabled:opacity-40"
          :disabled="disabled || mode === 'total'"
          @click="step(1)"
        ><Icon name="lucide:arrow-down" class="size-4" />Próxima</NuxtButton>
        <NuxtButton
          v-else-if="rowIndex === 2"
          size="xl"
          color="neutral"
          variant="ghost"
          class="inline-flex h-16 items-center justify-center rounded-lg bg-secondary op-label font-semibold transition disabled:opacity-40"
          :disabled="disabled"
          @click="clear"
        >Limpar</NuxtButton>
        <NuxtButton
          v-else
          size="xl"
          color="neutral"
          variant="ghost"
          class="inline-flex h-16 items-center justify-center gap-1.5 rounded-lg bg-secondary op-label font-semibold transition disabled:opacity-40"
          :disabled="disabled"
          @click="emit('note')"
        ><Icon name="lucide:message-square-text" class="size-4" />Observação</NuxtButton>
      </template>
    </div>
  </div>
</template>
