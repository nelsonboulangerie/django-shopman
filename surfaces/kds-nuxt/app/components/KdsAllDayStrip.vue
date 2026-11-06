<script setup lang="ts">
// "A FAZER" (prévia v4, nota 5): o que falta somando a fila INTEIRA, inclusive o "+N".
// Uma linha só, e nenhum chip cortado na borda (auditoria D10): cabem os que cabem,
// inteiros, e o resto vira "+N itens" no fim. Uma fila invisível mede a largura de
// cada chip; a linha de verdade mostra só os que cabem. O "+N itens" é BOTÃO: abre a
// lista do que ficou de fora ao toque (um `title` não abre no tablet).
import { fitAllDayChips, type KDSAllDayCount } from "~/presentation/board";

const props = defineProps<{ entries: KDSAllDayCount[] }>();

const GAP = 8;
const LABEL = 86 + GAP;
/** Lugar reservado para o "+N itens" quando nem todos cabem. */
const MORE = 96 + GAP;

const box = ref<HTMLElement | null>(null);
const measure = ref<HTMLElement | null>(null);
const { width } = useElementSize(box);
const visibleIndexes = ref<number[]>(props.entries.map((_, index) => index));

function recount() {
  const row = measure.value;
  if (!row) {
    visibleIndexes.value = props.entries.map((_, index) => index);
    return;
  }
  const widths = [...row.querySelectorAll<HTMLElement>("[data-measure-chip]")].map((chip) => chip.offsetWidth);
  visibleIndexes.value = fitAllDayChips(widths, width.value, { reserve: LABEL, more: MORE, gap: GAP });
}

watch([width, () => props.entries], () => nextTick(recount), { deep: true });
onMounted(() => nextTick(recount));

const visible = computed(() => {
  const shown = new Set(visibleIndexes.value);
  return props.entries.filter((_, index) => shown.has(index));
});
const hidden = computed(() => {
  const shown = new Set(visibleIndexes.value);
  return props.entries.filter((_, index) => !shown.has(index));
});
const hiddenLabel = computed(() => {
  const count = hidden.value.length;
  return count === 1 ? "+1 item" : `+${count} itens`;
});
const hiddenList = computed(() => hidden.value.map((entry) => `${entry.qty}× ${entry.name}`).join(", "));
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
    <NuxtPopover v-if="hidden.length" :content="{ side: 'bottom', align: 'start' }">
      <NuxtButton
        color="neutral"
        variant="ghost"
        class="shrink-0 font-semibold"
        :label="hiddenLabel"
        :aria-label="`A fazer, ${hiddenLabel.slice(1)} fora da linha: ${hiddenList}`"
        data-kds-all-day-more
      />
      <template #content>
        <ul class="flex max-h-[60vh] flex-col gap-1 overflow-y-auto p-3" data-kds-all-day-hidden>
          <li v-for="entry in hidden" :key="entry.name" class="flex items-baseline gap-2">
            <b class="text-lg tabular-nums">{{ entry.qty }}×</b>
            <span class="op-body font-medium">{{ entry.name }}</span>
          </li>
        </ul>
      </template>
    </NuxtPopover>
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
