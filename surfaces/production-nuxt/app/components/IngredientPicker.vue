<script setup lang="ts">
// Casar uma linha da BOM com um ingrediente do sistema. É escolha numa lista longa, com
// busca: `NuxtSelectMenu`. A busca vai ao servidor (GET recipes/ingredients/?q=, com
// debounce no composable), então o filtro local fica desligado (`ignore-filter`);
// quando a captura já trouxe candidatos, eles aparecem antes de qualquer digitação.
// O resultado pode ser comprado ou produzido por outra receita. A origem não muda
// o gesto do operador: ele busca e escolhe um ingrediente.
import type { IngredientOptionProjection } from "~/types/recipeBook";

const props = defineProps<{
  /** SKU casado ("" = sem ingrediente). */
  modelValue: string;
  /** Nome exibido para o SKU casado (o campo mostra nome, não código). */
  matchedName?: string;
  /** Candidatos sugeridos pela captura (aparecem antes de digitar). */
  candidates?: IngredientOptionProjection[];
  placeholder?: string;
  disabled?: boolean;
  autoOpen?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  select: [option: IngredientOptionProjection];
}>();

const { options, pending, run, search, reset } = useIngredientSearch();
const term = ref("");
const open = ref(false);
watch(term, (value) => search(value));
watch(
  () => props.autoOpen,
  (shouldOpen) => {
    if (shouldOpen) nextTick(() => { open.value = true; });
  },
  { immediate: true },
);
watch(open, (isOpen) => {
  if (isOpen && !props.candidates?.length && !options.value.length && !pending.value) void run("");
});

interface PickerItem {
  value: string;
  label: string;
  description?: string;
  option: IngredientOptionProjection | null;
}

const items = computed<PickerItem[]>(() => {
  const list = term.value.trim() ? options.value : (props.candidates?.length ? props.candidates : options.value);
  const rows: PickerItem[] = list.map((option) => ({
    value: option.sku,
    label: option.name,
    description: option.sku,
    option,
  }));
  // O ingrediente já casado continua na lista, para o campo mostrar o nome dele.
  if (props.modelValue && !rows.some((row) => row.value === props.modelValue)) {
    rows.unshift({
      value: props.modelValue,
      label: props.matchedName || props.modelValue,
      description: props.matchedName ? props.modelValue : undefined,
      option: null,
    });
  }
  return rows;
});

function onUpdate(value: string | null | undefined) {
  const option = value ? items.value.find((row) => row.value === value)?.option : null;
  term.value = "";
  reset();
  if (!value) {
    emit("update:modelValue", "");
    return;
  }
  emit("update:modelValue", value);
  if (option) emit("select", option);
}

const touch = useTouchPointer();
</script>

<template>
  <NuxtSelectMenu
    v-model:open="open"
    v-model:search-term="term"
    :model-value="modelValue || undefined"
    :items="items"
    value-key="value"
    ignore-filter
    :loading="pending"
    :clear="!disabled"
    :disabled="disabled"
    :placeholder="placeholder || 'Buscar ingrediente…'"
    :search-input="{ autofocus: !touch, placeholder: 'Buscar ingrediente' }"
    class="w-full min-w-0"
    aria-label="Ingrediente"
    @update:model-value="onUpdate"
  >
    <template #item-label="{ item }">
      <span class="flex min-w-0 items-center gap-2">
        <span class="truncate">{{ item.label }}</span>
        <NuxtBadge v-if="item.option?.is_part" color="neutral" label="Receita" />
      </span>
    </template>
    <template #empty>
      {{ pending ? "Buscando…" : "Nenhum ingrediente encontrado." }}
    </template>
  </NuxtSelectMenu>
</template>
