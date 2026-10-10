<script setup lang="ts">
// Square icon action (size-control, 44 px) das barras de trabalho do operador — refresh, export,
// print, theme, view toggles. One neutral resting style; `active` tints it like a
// pressed segment, `spinning` animates the glyph (refresh-in-flight). Renders a
// native <button> as root so parent `@click`/`:disabled` fall through.
// Visual da suíte (`suite:`, UX-KIT-V1): fundo de cartão, ícone de 20px, como os
// controles do cabeçalho de `orders-board3.html`.
defineProps<{
  icon: string;
  label: string;
  active?: boolean;
  spinning?: boolean;
}>();
</script>

<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    class="grid size-control shrink-0 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-50 suite:bg-card suite:text-foreground"
    :class="active ? 'bg-accent text-foreground' : ''"
  >
    <Icon :name="icon" class="size-4 suite:size-5" :class="spinning ? 'animate-spin' : ''" />
  </button>
</template>
