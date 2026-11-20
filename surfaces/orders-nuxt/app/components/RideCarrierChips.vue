<script setup lang="ts">
// "Quem leva" (M3, #2526): uma linha de opções por corrida. O serviço padrão do Admin vem
// primeiro e marcado; cada pessoa da casa na escala vem depois, com o estado e o valor
// da tabela. Um toque troca. A página é dona da escolha: aqui só se desenha e devolve.
import { DEFAULT_CARRIER, chipLine, type CarrierChip } from "~/presentation/houseCouriers";

const props = defineProps<{
  chips: CarrierChip[];
  modelValue: string;
  /** "Quem leva a corrida A": o nome do grupo para o leitor de tela. */
  label: string;
  notice?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [key: string] }>();

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
    <p v-if="notice" class="op-micro text-warning" data-ride-carrier-notice>{{ notice }}</p>
  </div>
</template>
