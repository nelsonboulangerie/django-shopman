<script setup lang="ts">
// Work toolbar das superfícies de operador (Pedidos, Catálogo, Marketing). Full-bleed,
// compact bar that sits under the hub nav. The default slot holds the primary controls
// (search + filter chips, left-aligned); the `end` slot holds the view/action cluster
// (pushed right, e com `flex-wrap` para o cluster quebrar em vez de transbordar em
// tela estreita). Os boards compõem a barra a partir das mesmas primitivas do kit
// (UiSearchInput, UiFilterChip, UiIconButton) so they read as one design language,
// not copy-paste.
</script>

<template>
  <div class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b bg-card/60 px-4 py-2 print:hidden">
    <slot />
    <div v-if="$slots.end" class="ml-auto flex flex-wrap items-center gap-1.5">
      <slot name="end" />
    </div>
  </div>
</template>
