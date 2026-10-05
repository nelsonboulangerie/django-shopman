<script setup lang="ts" generic="T extends ChoiceValue">
/**
 * Seletor pesquisável canônico da suíte.
 *
 * Popover, combobox, lista, foco, teclado, seleção e dispensa pertencem ao
 * `NuxtSelectMenu` (Reka UI). O wrapper mantém apenas os requisitos medidos no
 * trabalho de campo: busca automática em listas longas, múltiplos termos em
 * qualquer ordem, acentos ignorados, palavras-chave invisíveis e nome acessível
 * que combina o campo com o valor atual.
 */
import { computed, nextTick, ref, useAttrs, useId, useTemplateRef } from "vue";

import { SEARCH_THRESHOLD, filterOptions, isSearchable, resultsAnnouncement, selectedOption } from "../presentation/choice";
import type { ChoiceOption, ChoiceValue } from "../types/choice";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    modelValue?: T;
    options: ChoiceOption<T>[];
    placeholder?: string;
    labelledBy?: string;
    label?: string;
    disabled?: boolean;
    searchable?: boolean;
    searchThreshold?: number;
    searchPlaceholder?: string;
    emptyText?: string;
  }>(),
  {
    placeholder: "Selecione",
    searchable: undefined,
    searchThreshold: SEARCH_THRESHOLD,
    searchPlaceholder: "Buscar",
    emptyText: "Nenhum resultado",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: T];
  change: [option: ChoiceOption<T>];
}>();

const slots = defineSlots<{
  option?: (scope: { option: ChoiceOption<T>; active: boolean; selected: boolean }) => unknown;
  value?: (scope: { option: ChoiceOption<T> }) => unknown;
  empty?: (scope: { query: string }) => unknown;
}>();

const attrs = useAttrs();
const picker = useTemplateRef<{ triggerRef?: HTMLElement }>("picker");
const uid = useId();
const valueId = `${uid}-value`;
const labelId = `${uid}-label`;

const query = ref("");
const activeValue = ref<ChoiceValue>();
const chosen = computed(() => selectedOption(props.options, props.modelValue));
const hasSearch = computed(() =>
  props.searchable ?? isSearchable(props.options.length, props.searchThreshold),
);
const filteredOptions = computed(() =>
  hasSearch.value ? filterOptions(props.options, query.value) : props.options,
);
const announcement = computed(() =>
  query.value ? resultsAnnouncement(filteredOptions.value.length) : "",
);

const labelSource = computed(() => props.labelledBy ?? (props.label ? labelId : undefined));
const triggerLabelledBy = computed(() =>
  labelSource.value ? `${labelSource.value} ${valueId}` : valueId,
);

function wrapSearchAtEdges(event: KeyboardEvent) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const target = event.currentTarget;
  if (!(target instanceof HTMLElement)) return;
  const listboxId = target.getAttribute("aria-controls");
  const options = listboxId
    ? document.getElementById(listboxId)?.querySelectorAll<HTMLElement>('[role="option"]:not([aria-disabled="true"])')
    : undefined;
  if (!options?.length) return;

  const activeId = target.getAttribute("aria-activedescendant");
  const atLast = event.key === "ArrowDown" && activeId === options[options.length - 1]?.id;
  const atFirst = event.key === "ArrowUp" && activeId === options[0]?.id;
  if (!atLast && !atFirst) return;

  // O padrão canônico não dá a volta. A suíte já oferecia esse atalho; convertemos
  // somente o gesto da borda em Home/End e deixamos o Reka executar o movimento.
  event.preventDefault();
  event.stopImmediatePropagation();
  void nextTick(() => {
    target.dispatchEvent(new KeyboardEvent("keydown", {
      key: atLast ? "Home" : "End",
      code: atLast ? "Home" : "End",
      bubbles: true,
      cancelable: true,
    }));
  });
}

const searchInput = computed(() =>
  hasSearch.value
    ? {
        placeholder: props.searchPlaceholder,
        "aria-labelledby": labelSource.value,
        "aria-label": labelSource.value ? undefined : props.label ?? props.searchPlaceholder,
        onKeydown: wrapSearchAtEdges,
      }
    : false,
);
const content = computed(() => ({
  position: "popper" as const,
  side: "bottom" as const,
  sideOffset: 4,
  collisionPadding: 8,
  "aria-labelledby": labelSource.value,
  "aria-label": labelSource.value ? undefined : "Opções",
}));
const ui = {
  base: "h-control w-full text-sm",
  content: "max-h-64",
  item: "min-h-control px-3 py-2.5 text-sm",
  itemDescription: "text-xs",
};

function onUpdate(value: T) {
  const option = props.options.find((candidate) => candidate.value === value);
  if (!option) return;
  emit("update:modelValue", value);
  emit("change", option);
}

function onHighlight(payload: { value: T } | undefined) {
  activeValue.value = payload?.value;
}

defineExpose({ focus: () => picker.value?.triggerRef?.focus() });
</script>

<template>
  <div data-slot="select" class="relative w-full">
    <span v-if="label && !labelledBy" :id="labelId" class="sr-only">{{ label }}</span>

    <NuxtSelectMenu
      ref="picker"
      v-bind="attrs"
      :model-value="modelValue"
      :items="filteredOptions"
      :disabled="disabled"
      :placeholder="placeholder"
      :search-input="searchInput"
      :content="content"
      :trailing-icon="hasSearch ? 'lucide:search' : undefined"
      :aria-labelledby="triggerLabelledBy"
      :ui="ui"
      class="w-full"
      value-key="value"
      label-key="label"
      description-key="hint"
      size="lg"
      color="neutral"
      variant="outline"
      ignore-filter
      highlight-on-hover
      v-model:search-term="query"
      data-shopman-slot="select-trigger"
      @update:model-value="onUpdate"
      @highlight="onHighlight"
    >
      <template #default>
        <span
          :id="valueId"
          :data-slot="chosen ? 'value' : 'placeholder'"
          class="min-w-0 truncate"
          :class="chosen ? 'font-medium' : 'text-muted'"
        >
          <slot v-if="chosen" name="value" :option="chosen">{{ chosen.label }}</slot>
          <template v-else>{{ placeholder }}</template>
        </span>
      </template>

      <template v-if="slots.option" #item="{ item }">
        <slot
          name="option"
          :option="item"
          :active="activeValue === item.value"
          :selected="item.value === modelValue"
        />
      </template>

      <template #empty="{ searchTerm }">
        <slot name="empty" :query="searchTerm">{{ emptyText }}</slot>
      </template>

      <template #content-bottom>
        <p
          role="status"
          aria-live="polite"
          class="px-3 text-xs text-muted"
          :class="announcement ? 'py-1.5' : 'sr-only'"
        >
          {{ announcement }}
        </p>
      </template>
    </NuxtSelectMenu>
  </div>
</template>
