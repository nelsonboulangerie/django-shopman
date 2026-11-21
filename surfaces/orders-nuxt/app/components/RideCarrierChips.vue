<script setup lang="ts">
// "Quem leva" (M3, #2526): uma linha de opções por corrida. O serviço padrão do Admin vem
// primeiro e marcado; cada pessoa da casa na escala vem depois, com o estado e o valor
// da tabela. Um toque troca. A página é dona da escolha: aqui só se desenha e devolve.
// M3c (#2899): com mais de 3 da casa na escala, o último chip vira "Outro da casa" e a
// lista aparece embaixo; escolhida a casa, a observação para o entregador (opcional),
// que a página do link mostra.
import { DEFAULT_CARRIER, NOTE_MAX, chipLine, type CarrierChip } from "~/presentation/houseCouriers";

const props = defineProps<{
  chips: CarrierChip[];
  /** O chip marcado (o "Outro da casa" quando o escolhido está na lista dele). */
  modelValue: string;
  /** "Quem leva a corrida A": o nome do grupo para o leitor de tela. */
  label: string;
  notice?: string;
  /** A lista do "Outro da casa" (vazia: não há). */
  others?: { label: string; value: string }[];
  /** O `ref` de quem foi escolhido na lista do "Outro da casa". */
  otherValue?: string;
  /** "Observação para Diego (opcional)"; vazio quando quem leva não é da casa. */
  noteLabel?: string;
  note?: string;
}>();
const emit = defineEmits<{
  "update:modelValue": [key: string];
  other: [ref: string];
  "update:note": [value: string];
}>();

// O rádio não aceita valor vazio; o serviço padrão ganha uma chave só da tela.
const SERVICE = "service";
const items = computed(() =>
  props.chips.map((chip) => ({
    value: chip.key === DEFAULT_CARRIER ? SERVICE : chip.key,
    label: chip.label,
    // O marcado leva o ✔ (como a cotação juntas×separadas): TaOn e Diego nunca se parecem.
    description: chipLine(chip),
  })),
);
const selected = computed(() => (props.modelValue === DEFAULT_CARRIER ? SERVICE : props.modelValue));
const otherChosen = computed(() => Boolean(props.others?.length) && props.others!.some((item) => item.value === props.otherValue));
</script>

<template>
  <div class="flex flex-col gap-1.5" data-ride-carrier>
    <NuxtRadioGroup
      :model-value="selected"
      :items="items"
      legend="Quem leva"
      :aria-label="label"
      orientation="horizontal"
      variant="card"
      indicator="hidden"
      class="tabular-nums [font-variant-emoji:text]"
      @update:model-value="(value: unknown) => emit('update:modelValue', value === SERVICE ? DEFAULT_CARRIER : String(value))"
    />
    <NuxtSelect
      v-if="otherChosen"
      :model-value="otherValue"
      :items="others"
      class="min-h-11 min-w-56 self-start"
      size="xl"
      :aria-label="`Outro da casa: ${label.toLowerCase()}`"
      data-ride-carrier-other
      @update:model-value="(value: string) => emit('other', value)"
    />
    <p v-if="notice" class="op-micro text-warning" data-ride-carrier-notice>{{ notice }}</p>
    <NuxtInput
      v-if="noteLabel"
      :model-value="note"
      :placeholder="noteLabel"
      :aria-label="noteLabel"
      :maxlength="NOTE_MAX"
      size="xl"
      icon="i-lucide-message-square-text"
      data-ride-carrier-note
      @update:model-value="(value: string | number) => emit('update:note', String(value ?? ''))"
    />
  </div>
</template>
