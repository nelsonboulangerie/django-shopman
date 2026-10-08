<script setup lang="ts">
// Barra de filtros universal (padrão Linear/Notion, plano SUITE-UX "Filtrar"): uma
// linha só, com os recortes ativos como chips e um "+ Filtro" que abre a lista de
// campos e, ao escolher um, o painel daquele campo no MESMO popover (dois passos,
// com voltar). O operador não perde o contexto e o popover nunca sai da tela.
//
// - Campo de lista (multi, single, boolean): marca vários valores, com contagem por
//   valor e busca quando a lista é longa (`needsSearch`).
// - Campo digitado (text, number-range, date-range): o valor e "Aplicar".
// - Cada campo aplicado vira um chip "Pagamento: Pix, Cartão ×". Tocar no chip
//   reabre a edição DAQUELE campo; o × remove; "Limpar filtros" tira todos.
// - No celular (abaixo de `sm`), a linha de chips rola na horizontal e o popover
//   vira painel de baixo com fundo escurecido.
//
// Genérica de propósito: não conhece o domínio. O app passa os campos e recebe de
// volta os filtros ativos; interpretar o valor é dele. Para guardar na URL, use
// `useRouteFilters` (ou `filtersToQuery`/`filtersFromQuery`).
//
// `touch`: a mesma barra no tamanho `md` oficial do Nuxt UI, com o envelope de toque
// do balcão (`min-h-control`, 44 px; 48 px em tablet touch) no gatilho, nos chips, no
// X e nos itens do painel. Sem ele, a barra usa `xs`, compacta para mouse, e só os
// itens do painel ganham o envelope no celular. O envelope é opt-in por esta prop:
// nenhuma regra CSS global infla os controles.
import {
  activeDimensions,
  chipLabel,
  clearDimension,
  isListType,
  isRangeType,
  isSelected,
  needsSearch,
  optionsFor,
  searchOptions,
  setValues,
  toggleOption,
} from "../presentation/filterBar";
import type { ActiveFilters, FilterDimension } from "../types/filters";

const props = withDefaults(
  defineProps<{
    dimensions: FilterDimension[];
    modelValue: ActiveFilters;
    /** Rótulo do gatilho. */
    label?: string;
    /** Tamanho `md` do Nuxt UI (balcão, tablet). Padrão: `xs` de mesa. */
    touch?: boolean;
  }>(),
  { label: "Filtro", touch: false },
);

const controlSize = computed(() =>
  props.touch ? ("md" as const) : ("xs" as const),
);
// Alvo de toque (main: `min-h-control` no `touch`; no celular os itens do painel são
// sempre de toque). A pilha do Gestor tinha deixado só o `md` (32 px): o PDV perdia
// o alvo de 44 px nas Encomendas.
const touchTarget = computed(() => (props.touch ? "min-h-control" : undefined));
const itemTarget = computed(() =>
  props.touch ? "min-h-control" : "max-sm:min-h-control",
);

const emit = defineEmits<{ "update:modelValue": [ActiveFilters] }>();

const open = ref(false);
// Campo aberto no 2º passo (null = lista de campos).
const step = ref<FilterDimension | null>(null);
const search = ref("");
// Rascunho dos campos digitados: só vira filtro no "Aplicar" (ou Enter).
const draft = ref<string[]>(["", ""]);

const chips = computed(() =>
  activeDimensions(props.dimensions, props.modelValue),
);
const hasFilters = computed(() => chips.value.length > 0);
const visibleOptions = computed(() =>
  step.value ? searchOptions(optionsFor(step.value), search.value) : [],
);

function onOpen(value: boolean) {
  if (value) step.value = null;
  open.value = value;
}

function close() {
  open.value = false;
  step.value = null;
}

function pickDimension(dimension: FilterDimension) {
  step.value = dimension;
  search.value = "";
  const current = props.modelValue[dimension.id] ?? [];
  draft.value = [current[0] ?? "", current[1] ?? ""];
}

/** Chip tocado: reabre o popover direto na edição daquele campo. */
function editDimension(dimension: FilterDimension) {
  open.value = true;
  pickDimension(dimension);
}

function pick(dimension: FilterDimension, value: string) {
  emit("update:modelValue", toggleOption(props.modelValue, dimension, value));
  // Multi-select fica aberto (marcar vários é um gesto só); os demais fecham.
  if (dimension.type !== "multi-select") close();
}

function applyDraft(dimension: FilterDimension) {
  const values =
    dimension.type === "text"
      ? [draft.value[0] ?? ""]
      : [draft.value[0] ?? "", draft.value[1] ?? ""];
  emit("update:modelValue", setValues(props.modelValue, dimension.id, values));
  close();
}

function remove(dimension: FilterDimension) {
  emit("update:modelValue", clearDimension(props.modelValue, dimension.id));
  if (step.value?.id === dimension.id) close();
}

function clearAll() {
  emit("update:modelValue", {});
  close();
}
</script>

<template>
  <div
    class="flex items-center gap-1.5 max-sm:no-scrollbar max-sm:flex-nowrap max-sm:overflow-x-auto sm:flex-wrap"
  >
    <!-- chips do recorte ativo: "campo: valores" (toque edita) + X -->
    <NuxtFieldGroup
      v-for="dimension in chips"
      :key="dimension.id"
      class="shrink-0"
      :data-filter-chip="dimension.id"
    >
      <NuxtButton
        color="neutral"
        variant="soft"
        :size="controlSize"
        :class="touchTarget"
        :label="chipLabel(dimension, modelValue)"
        :aria-label="`Editar filtro ${chipLabel(dimension, modelValue)}`"
        data-filter-edit
        @click="editDimension(dimension)"
      />
      <NuxtButton
        color="neutral"
        variant="soft"
        :size="controlSize"
        :class="touchTarget"
        icon="i-lucide-x"
        square
        :aria-label="`Remover filtro ${dimension.label}`"
        data-filter-remove
        @click="remove(dimension)"
      />
    </NuxtFieldGroup>

    <!-- gatilho + popover de dois passos -->
    <NuxtPopover :open="open" @update:open="onOpen">
      <NuxtButton
        class="shrink-0"
        :class="touchTarget"
        color="neutral"
        variant="outline"
        :size="controlSize"
        icon="i-lucide-list-filter"
        :label="label"
        data-filter-trigger
      />

      <template #content>
        <div
          class="w-72 max-w-[calc(100vw-2rem)] p-2"
          :aria-label="step ? `Filtrar por ${step.label}` : 'Escolher filtro'"
          data-filter-panel
        >
          <div v-if="!step" class="grid gap-1">
            <NuxtButton
              v-for="dimension in dimensions"
              :key="dimension.id"
              block
              color="neutral"
              variant="ghost"
              trailing-icon="i-lucide-chevron-right"
              :class="itemTarget"
              :label="dimension.label"
              :data-filter-dimension="dimension.id"
              @click="pickDimension(dimension)"
            />
          </div>

          <template v-else>
            <NuxtButton
              block
              color="neutral"
              variant="ghost"
              icon="i-lucide-chevron-left"
              :class="itemTarget"
              :label="step.label"
              data-filter-back
              @click="step = null"
            />
            <NuxtSeparator class="my-2" />

            <template v-if="isListType(step)">
              <div v-if="needsSearch(step)" class="mb-2">
                <NuxtInput
                  v-model="search"
                  type="search"
                  icon="i-lucide-search"
                  :placeholder="`Buscar em ${step.label}`"
                  :aria-label="`Buscar em ${step.label}`"
                  data-filter-search
                />
              </div>
              <div class="grid max-h-64 gap-1 overflow-auto">
                <NuxtButton
                  v-for="option in visibleOptions"
                  :key="option.value"
                  block
                  color="neutral"
                  :variant="
                    isSelected(modelValue, step, option.value)
                      ? 'soft'
                      : 'ghost'
                  "
                  :icon="
                    isSelected(modelValue, step, option.value)
                      ? 'i-lucide-check'
                      : undefined
                  "
                  :class="itemTarget"
                  :label="option.label"
                  :aria-pressed="isSelected(modelValue, step, option.value)"
                  :data-filter-option="`${step.id}:${option.value}`"
                  @click="pick(step, option.value)"
                >
                  <!-- A contagem é outra grandeza: fica à parte do rótulo, como no
                       `main`, e não costurada nele ("Pagas · 1"). -->
                  <template v-if="option.count !== undefined" #trailing>
                    <NuxtBadge
                      class="ms-auto tabular-nums"
                      color="neutral"
                      variant="soft"
                      :label="String(option.count)"
                    />
                  </template>
                </NuxtButton>
                <NuxtEmpty
                  v-if="!visibleOptions.length"
                  icon="i-lucide-search-x"
                  :title="
                    search
                      ? 'Nenhuma opção com essa busca'
                      : 'Nenhuma opção para escolher agora'
                  "
                  data-filter-empty
                />
              </div>
              <div v-if="step.type === 'multi-select'" class="mt-2">
                <NuxtButton
                  block
                  label="Pronto"
                  data-filter-done
                  @click="close"
                />
              </div>
            </template>

            <NuxtForm
              v-else
              :state="draft"
              class="space-y-2"
              data-filter-form
              @submit="applyDraft(step)"
            >
              <NuxtFormField v-if="step.type === 'text'" :label="step.label">
                <NuxtInput
                  v-model="draft[0]"
                  class="w-full"
                  type="search"
                  :placeholder="step.placeholder || step.label"
                  data-filter-input="text"
                />
              </NuxtFormField>
              <div v-else-if="isRangeType(step)" class="grid grid-cols-2 gap-2">
                <NuxtFormField label="De">
                  <NuxtInput
                    v-model="draft[0]"
                    class="w-full"
                    :type="step.type === 'date-range' ? 'date' : 'number'"
                    :placeholder="
                      step.type === 'number-range'
                        ? step.placeholder
                        : undefined
                    "
                    data-filter-input="from"
                  />
                </NuxtFormField>
                <NuxtFormField label="Até">
                  <NuxtInput
                    v-model="draft[1]"
                    class="w-full"
                    :type="step.type === 'date-range' ? 'date' : 'number'"
                    data-filter-input="to"
                  />
                </NuxtFormField>
              </div>
              <NuxtButton
                type="submit"
                block
                label="Aplicar"
                data-filter-apply
              />
            </NuxtForm>
          </template>
        </div>
      </template>
    </NuxtPopover>

    <NuxtButton
      v-if="hasFilters"
      class="shrink-0"
      color="neutral"
      variant="link"
      :size="controlSize"
      :class="touchTarget"
      label="Limpar filtros"
      data-filter-clear
      @click="clearAll"
    />
  </div>
</template>
