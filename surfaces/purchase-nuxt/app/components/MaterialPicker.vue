<script setup lang="ts">
import type { Material } from "~/types/purchase";

/**
 * Escolher o insumo com BUSCA, e não rolando uma lista de dezenas.
 *
 * Um `<select>` nativo com 56 insumos é castigo no celular: o operador tem a
 * caixa na mão, o entregador esperando, e precisa achar "Manteiga francesa"
 * arrastando. Aqui ele digita "mant" e acaba.
 *
 * Sem biblioteca de componente (convenção da casa): é um botão que abre um
 * painel com campo de texto e a lista filtrada. A busca ignora acento e casa
 * tanto pelo nome quanto pelo SKU — o operador às vezes lê o código da etiqueta.
 */
const props = defineProps<{
  materials: Material[];
  modelValue: string;
  placeholder?: string;
}>();

const emit = defineEmits<{ "update:modelValue": [sku: string] }>();

const open = ref(false);
const query = ref("");
const search = useTemplateRef<HTMLInputElement>("search");

const selected = computed(() => props.materials.find((item) => item.sku === props.modelValue) ?? null);

/** Sem acento e sem caixa: "manteiga" acha "Manteiga", "acucar" acha "Açúcar". */
function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

const results = computed(() => {
  const needle = fold(query.value.trim());
  if (!needle) return props.materials;
  const terms = needle.split(/\s+/);
  return props.materials.filter((material) => {
    const haystack = fold(`${material.name} ${material.sku} ${material.category}`);
    return terms.every((term) => haystack.includes(term));
  });
});

async function openPicker() {
  open.value = true;
  query.value = "";
  await nextTick();
  search.value?.focus();
}

function choose(sku: string) {
  emit("update:modelValue", sku);
  open.value = false;
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="flex h-11 w-full items-center justify-between gap-2 rounded-md border border-border bg-card px-3 text-left text-sm text-foreground"
      @click="openPicker"
    >
      <span class="truncate" :class="selected ? 'font-medium' : 'text-muted-foreground'">
        {{ selected?.name ?? (placeholder ?? "Escolher insumo") }}
      </span>
      <Icon name="lucide:search" class="size-4 shrink-0 text-muted-foreground" />
    </button>

    <!-- Fecha ao tocar fora. Um `fixed` inerte cobrindo a tela é mais confiável
         no celular que ouvir clique no documento, que briga com o scroll. -->
    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />

    <div v-if="open" class="absolute inset-x-0 top-full z-50 mt-1 rounded-md border border-border bg-card shadow-lg">
      <div class="border-b border-border p-2">
        <input
          ref="search"
          v-model="query"
          type="search"
          class="h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
          placeholder="Buscar insumo"
          @keydown.esc="open = false"
          @keydown.enter.prevent="results[0] && choose(results[0].sku)"
        />
      </div>
      <ul class="max-h-64 overflow-y-auto py-1">
        <li v-if="!results.length" class="px-3 py-3 text-sm text-muted-foreground">
          Nenhum insumo com "{{ query }}".
        </li>
        <li v-for="material in results" :key="material.sku">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm hover:bg-accent"
            :class="material.sku === modelValue ? 'font-semibold text-primary' : ''"
            @click="choose(material.sku)"
          >
            <span class="min-w-0">
              <span class="block truncate">{{ material.name }}</span>
              <span class="block truncate text-xs text-muted-foreground">{{ material.sku }} · conta em {{ material.unit }}</span>
            </span>
            <Icon v-if="material.sku === modelValue" name="lucide:check" class="size-4 shrink-0" />
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>
