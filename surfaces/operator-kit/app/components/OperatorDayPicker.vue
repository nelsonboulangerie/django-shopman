<script setup lang="ts">
// Tipo 1 dos controles de data da casa: "Escolha rápida de dia" (decisão do dono,
// 02/10/2026). Passo de wizard e campo de formulário: agendar e reagendar no PDV,
// recebimento no Compras.
//
// Quatro botões grandes, um toque escolhe:
//
//   Hoje        Amanhã      Sábado      Outra data
//   Qui 02/10   Sex 03/10   04/10       No calendário
//
// O terceiro é a próxima data DEPOIS de amanhã que o contexto permite (pula dia
// fechado, respeita min/max), nominada pelo dia da semana por extenso. Hoje e amanhã
// aparecem sempre; quando o contexto não deixa, ficam apagados com o motivo curto
// ("fechado"), para o operador ter a resposta de "e amanhã não dá?" sem procurar.
//
// "Outra data" revela o campo + calendário canônico da suíte (com min/max).
//
// Semântica: grupo de rádio (`role="radiogroup"`), uma parada de tabulação, setas
// andam entre as opções. A data é escolha exclusiva, não botão que fica apertado.
import { computed, ref } from "vue";

import { dayBlockReason, otherDayCaption, quickDayOptions, weekdayAndDate } from "../presentation/dates";

const props = withDefaults(
  defineProps<{
    /** A data escolhida ("YYYY-MM-DD"), ou "" quando nada foi escolhido. */
    modelValue: string;
    /** O hoje da LOJA. */
    today: string;
    min?: string;
    max?: string;
    /** Datas em que a casa opera (dia fechado fica de fora). */
    availableDates?: readonly string[] | null;
    /** Nome do grupo para leitor de tela ("Dia da retirada"). */
    label?: string;
    disabled?: boolean;
  }>(),
  { min: undefined, max: undefined, availableDates: null, label: "Dia", disabled: false },
);

const emit = defineEmits<{ "update:modelValue": [string] }>();

const context = computed(() => ({
  today: props.today,
  min: props.min,
  max: props.max,
  availableDates: props.availableDates,
}));
const options = computed(() => quickDayOptions(context.value));
const otherSelected = computed(
  () => !!props.modelValue && !options.value.some((option) => option.iso === props.modelValue),
);
const otherCaption = computed(() => otherDayCaption(props.modelValue, options.value));

const showOther = ref(false);
const otherError = ref("");
const buttons = ref<HTMLButtonElement[]>([]);

function pick(iso: string, reason: string) {
  if (props.disabled || reason) return;
  showOther.value = false;
  otherError.value = "";
  if (iso !== props.modelValue) emit("update:modelValue", iso);
}

function openOther() {
  if (props.disabled) return;
  showOther.value = true;
  otherError.value = "";
}

function pickOther(iso: string) {
  if (!iso) return;
  const reason = dayBlockReason(iso, context.value);
  if (reason) {
    otherError.value = `${weekdayAndDate(iso)}: ${reason}. Escolha outro dia.`;
    return;
  }
  otherError.value = "";
  if (iso !== props.modelValue) emit("update:modelValue", iso);
}

// Uma parada de tabulação: a escolhida, ou a primeira que se escolhe.
const tabStop = computed(() => {
  const chosen = options.value.findIndex((option) => option.iso === props.modelValue);
  if (chosen >= 0) return chosen;
  if (otherSelected.value) return 3;
  const firstFree = options.value.findIndex((option) => !option.reason);
  return firstFree >= 0 ? firstFree : 3;
});

function move(from: number, delta: number) {
  const total = 4;
  let index = from;
  for (let step = 0; step < total; step += 1) {
    index = (index + delta + total) % total;
    if (index === 3 || !options.value[index]!.reason) break;
  }
  buttons.value[index]?.focus();
}

function onKey(event: KeyboardEvent, index: number) {
  if (event.key === "ArrowRight" || event.key === "ArrowDown") {
    event.preventDefault();
    move(index, 1);
  } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
    event.preventDefault();
    move(index, -1);
  }
}

const tileClass = (selected: boolean, blocked: boolean) => [
  "flex min-h-control flex-col items-start justify-center rounded-md border px-3 py-2 text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  blocked
    ? "cursor-not-allowed border-dashed border-border text-muted-foreground opacity-60"
    : selected
      ? "border-primary bg-primary/5 text-foreground"
      : "border-border bg-background text-foreground hover:bg-accent",
];
</script>

<template>
  <div class="grid gap-2" data-day-picker>
    <div
      role="radiogroup"
      :aria-label="label"
      :aria-disabled="disabled || undefined"
      class="grid grid-cols-2 gap-2 sm:grid-cols-4"
    >
      <button
        v-for="(option, index) in options"
        :key="option.key"
        ref="buttons"
        type="button"
        role="radio"
        :aria-checked="modelValue === option.iso"
        :disabled="!!option.reason || disabled"
        :tabindex="tabStop === index ? 0 : -1"
        :class="tileClass(modelValue === option.iso, !!option.reason || disabled)"
        :aria-label="`${option.title}, ${option.caption}`"
        :data-day-option="option.key"
        :data-day-iso="option.iso"
        @click="pick(option.iso, option.reason)"
        @keydown="onKey($event, index)"
      >
        <span class="text-base font-semibold leading-tight" :class="modelValue === option.iso ? 'text-primary' : ''">
          {{ option.title }}
        </span>
        <span class="text-xs tabular-nums text-muted-foreground">{{ option.caption }}</span>
      </button>
      <button
        ref="buttons"
        type="button"
        role="radio"
        :aria-checked="otherSelected"
        :aria-expanded="showOther"
        :disabled="disabled"
        :tabindex="tabStop === 3 ? 0 : -1"
        :class="tileClass(otherSelected, disabled)"
        :aria-label="`Outra data, ${otherCaption}`"
        data-day-option="other"
        @click="openOther"
        @keydown="onKey($event, 3)"
      >
        <span class="text-base font-semibold leading-tight" :class="otherSelected ? 'text-primary' : ''">Outra data</span>
        <span class="text-xs tabular-nums text-muted-foreground">{{ otherCaption }}</span>
      </button>
    </div>

    <label v-if="showOther" class="grid gap-1 text-sm">
      <span class="text-xs font-medium text-muted-foreground">Escolha a data</span>
      <UiDateField
        :model-value="otherSelected ? modelValue : ''"
        :min="min"
        :max="max"
        :disabled="disabled"
        :label="`Outra data para ${label.toLocaleLowerCase('pt-BR')}`"
        data-day-other-input
        @update:model-value="pickOther"
      />
    </label>
    <p v-if="otherError" class="text-xs font-medium text-destructive" role="alert" data-day-other-error>
      {{ otherError }}
    </p>
  </div>
</template>
