<script setup lang="ts">
// Seletor de colunas — botão discreto na toolbar que abre a lista de colunas
// opcionais com marcação. Mesmo desenho de dropdown da FilterBar (fecha ao clicar
// fora / Esc), para as duas ferramentas da toolbar se comportarem igual.
//
// Genérico de propósito: não conhece o domínio. O app passa as colunas que PODEM
// sumir — a coluna obrigatória fica de fora da lista e por isso é inocultável.
import {
  hideAll,
  isVisible,
  showAll,
  toggleColumn,
  visibleCount,
} from "../presentation/columnPicker";
import type { ColumnOption, HiddenColumns } from "../types/columns";

const props = withDefaults(
  defineProps<{
    columns: ColumnOption[];
    /** Colunas ocultas, por id (v-model). */
    modelValue: HiddenColumns;
    /** Rótulo do gatilho. */
    label?: string;
  }>(),
  { label: "Colunas" },
);

const emit = defineEmits<{ "update:modelValue": [HiddenColumns] }>();

const open = ref(false);

const shown = computed(() => visibleCount(props.columns, props.modelValue));
const total = computed(() => props.columns.length);
// O gatilho só vira "3 de 7" quando há recorte: sem coluna oculta ele fica quieto,
// como qualquer controle que não está fazendo nada.
const hasHidden = computed(() => shown.value < total.value);

function toggle(id: string) {
  emit("update:modelValue", toggleColumn(props.modelValue, id));
}
</script>

<template>
  <NuxtPopover v-model:open="open">
    <NuxtButton
      color="neutral"
      :variant="hasHidden ? 'soft' : 'outline'"
      icon="i-lucide-columns-3"
      :label="hasHidden ? `${label} ${shown}/${total}` : label"
      :title="
        hasHidden ? `${shown} de ${total} colunas visíveis` : 'Escolher colunas'
      "
    />
    <template #content>
      <div class="w-56 p-2">
        <NuxtFieldGroup class="w-full">
          <NuxtButton
            color="neutral"
            variant="ghost"
            label="Mostrar todas"
            :disabled="!hasHidden"
            @click="emit('update:modelValue', showAll())"
          />
          <NuxtButton
            color="neutral"
            variant="ghost"
            label="Esconder todas"
            :disabled="shown === 0"
            @click="emit('update:modelValue', hideAll(columns))"
          />
        </NuxtFieldGroup>
        <NuxtSeparator class="my-2" />
        <div class="max-h-64 space-y-1 overflow-auto">
          <NuxtCheckbox
            v-for="column in columns"
            :key="column.id"
            :model-value="isVisible(modelValue, column.id)"
            :label="column.label"
            @update:model-value="toggle(column.id)"
          />
        </div>
      </div>
    </template>
  </NuxtPopover>
</template>
