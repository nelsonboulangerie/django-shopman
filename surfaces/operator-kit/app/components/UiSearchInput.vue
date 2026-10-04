<script setup lang="ts">
// Search box das barras de trabalho do operador — icon affordance + clear button +
// expand-on-focus. Todos os boards usam (Pedidos: pedidos; Catálogo: produto/SKU;
// Marketing: campanhas), so width and behaviour are identical. Exposes focus() for
// the "/" keyboard shortcut. `h-control`/`size-control` = 44 px do operator-theme.css.
//
// `shortcut` ENSINA a tecla dentro do campo (a busca das prévias v3, `_search3.html`:
// "/" à direita, some quando há texto). Visual da suíte (`suite:`, UX-KIT-V1): largura
// fixa de 22rem do tablet para cima (a busca é o controle principal da linha, não
// cresce no foco), ocupa a linha inteira no celular, texto de 15px.
withDefaults(
  defineProps<{
    modelValue: string;
    placeholder?: string;
    ariaLabel?: string;
    /** Tecla que leva ao campo, mostrada nele enquanto está vazio ("/"). */
    shortcut?: string;
  }>(),
  {
    placeholder: "Buscar…",
    ariaLabel: "Buscar",
    shortcut: "",
  },
);
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const input = ref<HTMLInputElement | null>(null);
defineExpose({ focus: () => input.value?.focus() });
</script>

<template>
  <div class="relative suite:w-full suite:md:w-[22rem]">
    <Icon name="lucide:search" class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground suite:left-3" />
    <input
      ref="input"
      :value="modelValue"
      type="search"
      inputmode="search"
      :placeholder="placeholder"
      :aria-label="ariaLabel"
      :aria-keyshortcuts="shortcut || undefined"
      class="h-control w-44 rounded-md border bg-card pl-8 pr-12 text-sm outline-none transition-[width,box-shadow] focus:w-56 focus:ring-1 focus:ring-ring sm:w-52 sm:focus:w-64 suite:w-full suite:border-input suite:pl-9 suite:text-[15px] suite:placeholder:text-muted-foreground suite:focus:w-full suite:focus:ring-2 suite:sm:w-full suite:sm:focus:w-full suite:[&::-webkit-search-cancel-button]:appearance-none"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <kbd
      v-if="shortcut && !modelValue"
      class="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground pointer-fine:md:block"
      aria-hidden="true"
      data-search-shortcut
    >{{ shortcut }}</kbd>
    <button
      v-if="modelValue"
      type="button"
      class="absolute right-0 top-1/2 grid size-control -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground"
      aria-label="Limpar busca"
      @click="emit('update:modelValue', '')"
    >
      <Icon name="lucide:x" class="size-3.5" />
    </button>
  </div>
</template>
