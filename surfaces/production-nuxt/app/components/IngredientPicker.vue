<script setup lang="ts">
// Casar um ingrediente com um insumo do sistema. Campo de texto que busca em
// GET recipes/ingredients/?q= (debounce) e mostra a lista logo abaixo; quando a
// captura já trouxe candidatos, eles aparecem antes de qualquer digitação. O valor
// é o SKU escolhido; "" = ainda sem insumo (permitido em rascunho, §3).
// A lista é absoluta dentro de um wrapper `relative` — o pai não pode recortar
// (sem overflow-x-auto em volta do editor).
import type { IngredientOptionProjection } from "~/types/recipeBook";

const props = defineProps<{
  /** SKU casado ("" = sem insumo). */
  modelValue: string;
  /** Nome exibido para o SKU casado (o cartão mostra nome, não código). */
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
const open = ref(false);

const list = computed<IngredientOptionProjection[]>(() =>
  term.value.trim() ? options.value : (props.candidates ?? []),
);

function onInput(event: Event) {
  term.value = (event.target as HTMLInputElement).value;
  search(term.value);
  open.value = true;
}

function choose(option: IngredientOptionProjection) {
  emit("update:modelValue", option.sku);
  emit("select", option);
  term.value = "";
  reset();
  open.value = false;
}

function clear() {
  emit("update:modelValue", "");
  term.value = "";
  reset();
}

function onBlur() {
  // Deixa o clique na lista acontecer antes de fechar.
  setTimeout(() => {
    open.value = false;
  }, 150);
}
</script>

<template>
  <div class="relative min-w-0">
    <div v-if="modelValue" class="flex h-9 items-center gap-1.5 rounded-md border bg-muted/40 px-2 text-sm">
      <Icon name="lucide:link" class="size-3.5 shrink-0 text-muted-foreground" />
      <span class="truncate font-medium">{{ matchedName || modelValue }}</span>
      <span v-if="matchedName" class="hidden truncate font-mono text-xs text-muted-foreground sm:inline">{{
        modelValue
      }}</span>
      <button
        v-if="!disabled"
        type="button"
        class="ml-auto grid size-6 shrink-0 place-items-center rounded text-muted-foreground transition hover:text-foreground"
        aria-label="Desfazer o insumo"
        title="Desfazer o insumo"
        @click="clear"
      >
        <Icon name="lucide:x" class="size-3.5" />
      </button>
    </div>
    <template v-else>
      <input
        :value="term"
        type="text"
        autocomplete="off"
        :placeholder="placeholder || 'Buscar insumo…'"
        :disabled="disabled"
        class="h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground outline-none transition focus:ring-1 focus:ring-ring"
        aria-label="Buscar insumo"
        @input="onInput"
        @focus="open = true"
        @blur="onBlur"
        @keydown.escape="open = false"
      />
      <ul
        v-if="open && (list.length || pending || term.trim())"
        class="absolute left-0 right-0 top-full z-20 mt-1 max-h-56 overflow-auto rounded-md border bg-card py-1 text-sm shadow-lg"
        role="listbox"
      >
        <li v-if="pending" class="px-3 py-1.5 text-muted-foreground">Buscando…</li>
        <li v-else-if="!list.length" class="px-3 py-1.5 text-muted-foreground">Nenhum insumo encontrado.</li>
        <li v-for="option in list" :key="option.sku" role="option" :aria-selected="false">
          <button
            type="button"
            class="flex w-full items-center gap-2 px-3 py-1.5 text-left transition hover:bg-accent"
            @mousedown.prevent="choose(option)"
          >
            <span class="min-w-0 flex-1 truncate">{{ option.name }}</span>
            <UiBadge v-if="option.is_part" variant="outline" class="px-1.5 py-0 text-xs">Parte</UiBadge>
            <span class="shrink-0 font-mono text-xs text-muted-foreground">{{ option.sku }}</span>
          </button>
        </li>
      </ul>
    </template>
  </div>
</template>
