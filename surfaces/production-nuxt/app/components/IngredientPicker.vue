<script setup lang="ts">
// Casar um ingrediente com um insumo do sistema. É escolha numa lista longa, com
// busca: `NuxtSelectMenu`. A busca vai ao servidor (GET recipes/ingredients/?q=, com
// debounce no composable), então o filtro local fica desligado (`ignore-filter`);
// quando a captura já trouxe candidatos, eles aparecem antes de qualquer digitação.
// O valor é o SKU escolhido; "" = ainda sem insumo (permitido em rascunho, §3), e o
// "limpar" do campo desfaz o insumo.
import type { IngredientOptionProjection } from "~/types/recipeBook";

const props = defineProps<{
  /** SKU casado ("" = sem insumo). */
  modelValue: string;
  /** Nome exibido para o SKU casado (o campo mostra nome, não código). */
  matchedName?: string;
  /** Candidatos sugeridos pela captura (aparecem antes de digitar). */
  candidates?: IngredientOptionProjection[];
  placeholder?: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  select: [option: IngredientOptionProjection];
}>();

const { options, pending, search, reset } = useIngredientSearch();
const term = ref("");
watch(term, (value) => search(value));

interface PickerItem {
  value: string;
  label: string;
  description?: string;
  option: IngredientOptionProjection | null;
}

const items = computed<PickerItem[]>(() => {
  const list = term.value.trim() ? options.value : (props.candidates ?? []);
  const rows: PickerItem[] = list.map((option) => ({
    value: option.sku,
    label: option.name,
    description: option.sku,
    option,
  }));
  // O insumo já casado continua na lista, para o campo mostrar o nome dele.
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
  term.value = "";
  reset();
  if (!value) {
    emit("update:modelValue", "");
    return;
  }
  emit("update:modelValue", value);
  const option = items.value.find((row) => row.value === value)?.option;
  if (option) emit("select", option);
}

const touch = useTouchPointer();
</script>

<template>
  <NuxtSelectMenu
    v-model:search-term="term"
    :model-value="modelValue || undefined"
    :items="items"
    value-key="value"
    ignore-filter
    :loading="pending"
    :clear="!disabled"
    :disabled="disabled"
    :placeholder="placeholder || 'Buscar insumo…'"
    :search-input="{ autofocus: !touch, placeholder: 'Buscar insumo' }"
    class="w-full min-w-0"
    aria-label="Insumo"
    @update:model-value="onUpdate"
  >
    <template #item-label="{ item }">
      <span class="flex min-w-0 items-center gap-2">
        <span class="truncate">{{ item.label }}</span>
        <NuxtBadge v-if="item.option?.is_part" color="neutral" label="Parte" />
      </span>
    </template>
    <template #empty>
      {{ pending ? "Buscando…" : "Nenhum insumo encontrado." }}
    </template>
  </NuxtSelectMenu>
</template>
