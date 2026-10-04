<script setup lang="ts">
// O período no celular (prévia `depois-marketing-bi-celular` (b), pino 6): um chip na
// barra de cima que diz a janela ("28D ⌄"), com as mesmas opções do desktop num
// painel (as granularidades, as janelas móveis e o personalizado). A janela é a mesma
// da URL (`useBiWindow`): trocar aqui troca em todas as seções.
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import {
  PERIOD_PRESETS_CALENDAR,
  PERIOD_PRESETS_ROLLING,
  customPeriodError,
} from "../../../operator-kit/app/presentation/dates";

const { selection, range, bounds, setPreset, applyCustom } = useBiWindow();

const open = ref(false);
const from = ref("");
const to = ref("");

const chipLabel = computed(() => {
  if (selection.value.preset === "custom") return `${range.value.date_from.slice(8, 10)}/${range.value.date_from.slice(5, 7)}+`;
  const preset = [...PERIOD_PRESETS_ROLLING, ...PERIOD_PRESETS_CALENDAR].find((item) => item.key === selection.value.preset);
  return preset?.label ?? "28D";
});
const customError = computed(() => (from.value && to.value ? customPeriodError(from.value, to.value, bounds.value) : ""));

watch(open, (value) => {
  if (!value) return;
  from.value = range.value.date_from;
  to.value = range.value.date_to;
});

function pick(key: string) {
  setPreset(key);
  open.value = false;
}

function submitCustom() {
  if (!from.value || !to.value || customError.value) return;
  applyCustom(from.value, to.value);
  open.value = false;
}

const CHIP = "inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border px-3 op-label font-semibold tnum transition";
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        class="mr-1 inline-flex h-10 items-center gap-1 rounded-full border border-primary/40 bg-primary/10 px-3 op-label font-semibold tnum"
        :aria-label="`Período de análise: ${chipLabel}`"
        data-bi-period-chip
      >
        {{ chipLabel }}
        <Icon name="lucide:chevron-down" class="size-4" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        side="bottom"
        align="end"
        :side-offset="6"
        :collision-padding="8"
        class="z-50 w-[min(22rem,calc(100vw-1rem))] rounded-lg border bg-popover p-3 text-popover-foreground shadow-lg outline-hidden"
        data-bi-period-panel
      >
        <p class="mb-1.5 op-eyebrow text-muted-foreground">Últimos</p>
        <div class="grid grid-cols-4 gap-1.5">
          <button
            v-for="preset in PERIOD_PRESETS_ROLLING"
            :key="preset.key"
            type="button"
            :class="[CHIP, selection.preset === preset.key ? 'border-primary bg-primary/10' : 'border-border bg-card']"
            :aria-label="preset.title"
            @click="pick(preset.key)"
          >{{ preset.label }}</button>
        </div>
        <p class="mt-3 mb-1.5 op-eyebrow text-muted-foreground">Período atual</p>
        <div class="grid grid-cols-4 gap-1.5">
          <button
            v-for="preset in PERIOD_PRESETS_CALENDAR"
            :key="preset.key"
            type="button"
            :class="[CHIP, selection.preset === preset.key ? 'border-primary bg-primary/10' : 'border-border bg-card']"
            @click="pick(preset.key)"
          >{{ preset.label }}</button>
        </div>
        <form class="mt-3 grid grid-cols-2 gap-2" @submit.prevent="submitCustom">
          <p class="col-span-2 op-eyebrow text-muted-foreground">Personalizado</p>
          <label class="flex flex-col gap-1 op-micro text-muted-foreground">De
            <input v-model="from" type="date" :max="bounds.max" class="min-h-11 rounded-md border border-border bg-card px-2 op-label text-foreground">
          </label>
          <label class="flex flex-col gap-1 op-micro text-muted-foreground">Até
            <input v-model="to" type="date" :max="bounds.max" class="min-h-11 rounded-md border border-border bg-card px-2 op-label text-foreground">
          </label>
          <p v-if="customError" class="col-span-2 op-micro text-destructive" role="alert">{{ customError }}</p>
          <UiButton type="submit" class="col-span-2" :disabled="!from || !to || Boolean(customError)">Ver este período</UiButton>
        </form>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
