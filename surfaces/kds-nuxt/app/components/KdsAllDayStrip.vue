<script setup lang="ts">
// "A FAZER" (prévia v4, nota 5): o que falta somando a fila INTEIRA, inclusive o "+N".
// Uma linha só, e nenhum chip cortado na borda (auditoria D10): cabem os que cabem,
// inteiros, e o resto vira "+N itens" no fim. Uma fila invisível mede a largura de
// cada chip; a linha de verdade mostra só os que cabem.
import type { KDSAllDayCount } from "~/presentation/board";

const props = defineProps<{ entries: KDSAllDayCount[] }>();

const GAP = 8;
const LABEL = 86 + GAP;
/** Lugar reservado para o "+N itens" quando nem todos cabem. */
const MORE = 96 + GAP;

const box = ref<HTMLElement | null>(null);
const measure = ref<HTMLElement | null>(null);
const { width } = useElementSize(box);
const visibleCount = ref(props.entries.length);

function recount() {
  const row = measure.value;
  if (!row || !width.value) {
    visibleCount.value = props.entries.length;
    return;
  }
  const widths = [...row.querySelectorAll<HTMLElement>("[data-measure-chip]")].map((chip) => chip.offsetWidth);
  const total = widths.reduce((sum, value) => sum + value + GAP, 0);
  if (LABEL + total <= width.value) {
    visibleCount.value = widths.length;
    return;
  }
  let used = LABEL + MORE;
  let count = 0;
  for (const value of widths) {
    if (used + value + GAP > width.value) break;
    used += value + GAP;
    count += 1;
  }
  visibleCount.value = count;
}

watch([width, () => props.entries], () => nextTick(recount), { deep: true });
onMounted(() => nextTick(recount));

const visible = computed(() => props.entries.slice(0, visibleCount.value));
const hidden = computed(() => props.entries.slice(visibleCount.value));
const hiddenLabel = computed(() => {
  const count = hidden.value.length;
  return count === 1 ? "+1 item" : `+${count} itens`;
});
const hiddenTitle = computed(() => hidden.value.map((entry) => `${entry.qty}× ${entry.name}`).join(", "));
</script>

<template>
  <div ref="box" class="relative flex min-h-8 shrink-0 items-center gap-2 overflow-hidden" data-kds-all-day>
    <span class="inline-flex w-[86px] shrink-0 items-center gap-1.5 op-eyebrow text-muted-foreground">
      <Icon name="lucide:clipboard-list" class="size-4" />A fazer
    </span>
    <span
      v-for="entry in visible"
      :key="entry.name"
      class="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-border bg-card px-3"
      data-kds-all-day-chip
    >
      <b class="text-lg tabular-nums">{{ entry.qty }}×</b>
      <span class="op-body font-medium whitespace-nowrap">{{ entry.name }}</span>
    </span>
    <span
      v-if="hidden.length"
      class="inline-flex h-8 shrink-0 items-center rounded-md px-2 op-label font-semibold text-muted-foreground"
      :title="hiddenTitle"
      data-kds-all-day-more
    >
      {{ hiddenLabel }}
    </span>
    <!-- Régua invisível: todos os chips, só para medir. -->
    <div
      ref="measure"
      class="pointer-events-none invisible absolute top-0 left-0 flex gap-2 whitespace-nowrap"
      aria-hidden="true"
    >
      <span
        v-for="entry in entries"
        :key="entry.name"
        class="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border px-3"
        data-measure-chip
      >
        <b class="text-lg tabular-nums">{{ entry.qty }}×</b>
        <span class="op-body font-medium">{{ entry.name }}</span>
      </span>
    </div>
  </div>
</template>
