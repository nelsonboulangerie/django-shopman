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
// `touch`: a mesma barra com alvos de toque de balcão (`min-h-control`, 44 px) no
// gatilho, nos chips, no X e nos itens do popover. Sem ele, a barra é a compacta
// de mesa (28 px), feita para mouse. No painel de baixo os itens são sempre de toque.
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
    /** Alvos de toque de 44 px (balcão, tablet). Padrão: compacta de mesa. */
    touch?: boolean;
  }>(),
  { label: "Filtro", touch: false },
);

const size = computed(() => (props.touch
  ? {
      chip: "min-h-control pl-3.5 pr-0.5 text-sm",
      remove: "size-10",
      removeIcon: "size-4",
      trigger: "min-h-control px-3.5 text-sm",
      triggerIcon: "size-4",
      menu: "sm:top-full sm:mt-1 sm:w-72",
      item: "min-h-control px-3 text-base",
    }
  : {
      chip: "h-7 pl-2.5 pr-1 text-xs",
      remove: "size-5",
      removeIcon: "size-3",
      trigger: "h-7 px-2.5 text-xs",
      triggerIcon: "size-3.5",
      menu: "sm:top-8 sm:w-64",
      item: "max-sm:min-h-control px-2.5 py-1.5 text-sm",
    }));

const emit = defineEmits<{ "update:modelValue": [ActiveFilters] }>();

const open = ref(false);
// Campo aberto no 2º passo (null = lista de campos).
const step = ref<FilterDimension | null>(null);
const root = ref<HTMLElement | null>(null);
const search = ref("");
// Rascunho dos campos digitados: só vira filtro no "Aplicar" (ou Enter).
const draft = ref<string[]>(["", ""]);

const chips = computed(() => activeDimensions(props.dimensions, props.modelValue));
const hasFilters = computed(() => chips.value.length > 0);
const visibleOptions = computed(() => (step.value ? searchOptions(optionsFor(step.value), search.value) : []));

function openMenu() {
  step.value = null;
  open.value = !open.value;
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
  const values = dimension.type === "text" ? [draft.value[0] ?? ""] : [draft.value[0] ?? "", draft.value[1] ?? ""];
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

// Fechar ao clicar fora / Esc — o popover é leve demais para merecer um portal.
function onDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return;
  if (root.value && !root.value.contains(event.target as Node)) close();
}

onMounted(() => document.addEventListener("pointerdown", onDocumentPointerDown));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onDocumentPointerDown));
</script>

<template>
  <div
    ref="root"
    class="relative flex items-center gap-1.5 max-sm:no-scrollbar max-sm:flex-nowrap max-sm:overflow-x-auto sm:flex-wrap"
    @keydown.esc="close"
  >
    <!-- chips do recorte ativo: "campo: valores" (toque edita) + X -->
    <span
      v-for="dimension in chips"
      :key="dimension.id"
      class="inline-flex shrink-0 items-center gap-1 rounded-full border border-border bg-accent/60 font-medium text-foreground"
      :class="size.chip"
      :data-filter-chip="dimension.id"
    >
      <button
        type="button"
        class="max-w-[18rem] truncate text-left"
        :aria-label="`Editar filtro ${chipLabel(dimension, modelValue)}`"
        data-filter-edit
        @click="editDimension(dimension)"
      >{{ chipLabel(dimension, modelValue) }}</button>
      <button
        type="button"
        class="grid shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-background hover:text-foreground"
        :class="size.remove"
        :aria-label="`Remover filtro ${dimension.label}`"
        data-filter-remove
        @click="remove(dimension)"
      >
        <Icon name="lucide:x" :class="size.removeIcon" />
      </button>
    </span>

    <!-- gatilho + popover de dois passos -->
    <button
      type="button"
      class="inline-flex shrink-0 items-center gap-1 rounded-full border border-dashed border-border font-medium text-muted-foreground transition hover:border-solid hover:bg-accent hover:text-foreground"
      :class="[size.trigger, open ? 'border-solid bg-accent text-foreground' : '']"
      aria-haspopup="dialog"
      :aria-expanded="open"
      data-filter-trigger
      @click="openMenu"
    >
      <Icon name="lucide:list-filter" :class="size.triggerIcon" />
      {{ label }}
    </button>

    <button
      v-if="hasFilters"
      type="button"
      class="inline-flex shrink-0 items-center rounded-full font-medium text-muted-foreground transition hover:text-foreground"
      :class="size.trigger"
      data-filter-clear
      @click="clearAll"
    >
      Limpar filtros
    </button>

    <!-- celular: fundo do painel de baixo (tocar fora fecha) -->
    <div v-if="open" class="fixed inset-0 z-40 bg-black/40 sm:hidden" aria-hidden="true" data-filter-backdrop @click="close" />

    <div
      v-if="open"
      role="dialog"
      :aria-label="step ? `Filtrar por ${step.label}` : 'Escolher filtro'"
      class="z-50 border border-border bg-card p-1 shadow-lg max-sm:fixed max-sm:inset-x-0 max-sm:bottom-0 max-sm:max-h-[80dvh] max-sm:overflow-auto max-sm:rounded-t-2xl max-sm:p-2 max-sm:pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:absolute sm:left-0 sm:rounded-lg"
      :class="size.menu"
      data-filter-panel
    >
      <!-- passo 1: campos -->
      <div v-if="!step" role="menu">
        <p class="px-2.5 pb-1 pt-1.5 text-xs font-medium text-muted-foreground sm:hidden">Filtrar por</p>
        <button
          v-for="dimension in dimensions"
          :key="dimension.id"
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-2 rounded text-left transition hover:bg-accent"
          :class="size.item"
          :data-filter-dimension="dimension.id"
          @click="pickDimension(dimension)"
        >
          <span class="truncate">{{ dimension.label }}</span>
          <Icon name="lucide:chevron-right" class="ml-auto size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </div>

      <!-- passo 2: o campo escolhido -->
      <template v-else>
        <button
          type="button"
          class="mb-0.5 flex w-full items-center gap-1 rounded text-left font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
          :class="touch ? 'min-h-control px-3 text-sm' : 'px-2 py-1.5 text-xs max-sm:min-h-control'"
          data-filter-back
          @click="step = null"
        >
          <Icon name="lucide:chevron-left" class="size-3.5" /> {{ step.label }}
        </button>

        <!-- lista: marcar valores, com busca quando é longa -->
        <template v-if="isListType(step)">
          <input
            v-if="needsSearch(step)"
            v-model="search"
            type="search"
            class="mb-1 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/40 max-sm:min-h-control"
            :placeholder="`Buscar em ${step.label}`"
            :aria-label="`Buscar em ${step.label}`"
            data-filter-search
          >
          <div role="menu" class="overflow-auto" :class="touch ? 'max-h-80' : 'max-h-64'">
            <button
              v-for="option in visibleOptions"
              :key="option.value"
              type="button"
              role="menuitemcheckbox"
              :aria-checked="isSelected(modelValue, step, option.value)"
              class="flex w-full items-center gap-2 rounded text-left transition hover:bg-accent"
              :class="size.item"
              :data-filter-option="`${step.id}:${option.value}`"
              @click="pick(step, option.value)"
            >
              <span
                class="grid size-4 shrink-0 place-items-center rounded border transition"
                :class="isSelected(modelValue, step, option.value)
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border'"
              >
                <Icon v-if="isSelected(modelValue, step, option.value)" name="lucide:check" class="size-3" />
              </span>
              <span class="truncate">{{ option.label }}</span>
              <span v-if="option.count !== undefined" class="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
                {{ option.count }}
              </span>
            </button>
            <p v-if="!visibleOptions.length" class="px-2.5 py-2 text-sm text-muted-foreground" data-filter-empty>
              {{ search ? "Nenhuma opção com essa busca." : "Nenhuma opção para escolher agora." }}
            </p>
          </div>
          <button
            v-if="step.type === 'multi-select'"
            type="button"
            class="mt-1 w-full rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 max-sm:min-h-control sm:hidden"
            data-filter-done
            @click="close"
          >
            Pronto
          </button>
        </template>

        <!-- campo digitado: texto ou intervalo De/Até -->
        <form v-else class="space-y-2 p-1.5" data-filter-form @submit.prevent="applyDraft(step)">
          <input
            v-if="step.type === 'text'"
            v-model="draft[0]"
            type="search"
            class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/40 max-sm:min-h-control"
            :placeholder="step.placeholder || step.label"
            :aria-label="step.label"
            data-filter-input="text"
          >
          <div v-else-if="isRangeType(step)" class="grid grid-cols-2 gap-2">
            <label class="grid gap-1 text-xs text-muted-foreground">
              De
              <input
                v-model="draft[0]"
                :type="step.type === 'date-range' ? 'date' : 'number'"
                class="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/40 max-sm:min-h-control"
                :placeholder="step.type === 'number-range' ? step.placeholder : undefined"
                data-filter-input="from"
              >
            </label>
            <label class="grid gap-1 text-xs text-muted-foreground">
              Até
              <input
                v-model="draft[1]"
                :type="step.type === 'date-range' ? 'date' : 'number'"
                class="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/40 max-sm:min-h-control"
                data-filter-input="to"
              >
            </label>
          </div>
          <button
            type="submit"
            class="w-full rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 max-sm:min-h-control"
            data-filter-apply
          >
            Aplicar
          </button>
        </form>
      </template>
    </div>
  </div>
</template>
