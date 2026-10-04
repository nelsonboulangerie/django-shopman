<script setup lang="ts">
// Filter pill das barras de trabalho do operador (Pedidos, Catálogo, Marketing).
// Active = solid `bg-primary` (the one unified choice; Catálogo's old `bg-foreground`
// is gone). Optional count suffix and an `icon` slot for the channel/collection glyph.
//
// ⚠️ `min-h-control` (44 px, `--spacing-control` do operator-theme.css) é alvo de
// toque, não estética.
//
// Visual da suíte (`suite:`, só dentro de `data-suite="v3"`, UX-KIT-V1): pílula clara
// com borda, o ativo com contorno e tinta de latão (`border-primary bg-primary/10`) em
// vez do preenchimento sólido, rótulo de 13px e contagem em cinza. Medida dos chips de
// `orders-board3.html`, mantendo os 44px de alvo. A cópia que o Marketing carregava tinha caído para `h-9`
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
    class="inline-flex min-h-control shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 suite:gap-2 suite:text-[13px]"
    :class="active
      ? 'border-transparent bg-primary text-primary-foreground suite:border-primary suite:bg-primary/10 suite:font-semibold suite:text-foreground'
      : 'text-muted-foreground hover:bg-accent hover:text-foreground suite:border-border suite:bg-card suite:text-foreground'"
  >
    <slot name="icon" />
    <slot />
    <span v-if="count != null" class="tabular-nums opacity-70 suite:font-normal suite:text-muted-foreground suite:opacity-100">{{ count }}</span>
  </button>
</template>
