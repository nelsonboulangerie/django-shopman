<script setup lang="ts">
// Filter pill das barras de trabalho do operador (Pedidos, Catálogo, Marketing).
// Active = solid `bg-primary` (the one unified choice; Catálogo's old `bg-foreground`
// is gone). Optional count suffix and an `icon` slot for the channel/collection glyph.
//
// ⚠️ `min-h-control` (44 px, `--spacing-control` do operator-theme.css) é alvo de
// toque, não estética. A cópia que o Marketing carregava tinha caído para `h-9`
// (36 px); nenhuma tela de lá a montava, então a regressão estava ARMADA, não no
// ar — que é justamente como a cópia cobra: em silêncio, no dia em que alguém usa.
defineProps<{
  active?: boolean;
  count?: number | null;
}>();
</script>

<template>
  <button
    type="button"
    class="inline-flex min-h-control shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
    :class="active ? 'border-transparent bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
  >
    <slot name="icon" />
    <slot />
    <span v-if="count != null" class="tabular-nums opacity-70">{{ count }}</span>
  </button>
</template>
