<script setup lang="ts">
// Card-fallback de produto sem foto: fundo tintado na cor da categoria
// primária, ícone Lucide genérico da categoria e o SKU abaixo do ícone.
// Sem cor/ícone da categoria, cai no par neutro (bg-muted + ícone padrão).
const props = defineProps<{
  color?: string | null
  icon?: string | null
  sku: string
  // Ícone quando a categoria não define um (varia por contexto de uso).
  fallbackIcon?: string
  iconClass?: string
}>()

const iconName = computed(() => (props.icon ? `lucide:${props.icon}` : props.fallbackIcon || 'lucide:croissant'))
const tintStyle = computed(() => (props.color ? { '--category-color': props.color } : undefined))
</script>

<template>
  <div
    class="flex size-full flex-col items-center justify-center gap-1"
    :class="color ? 'shop-category-tint' : 'bg-muted text-muted-foreground'"
    :style="tintStyle"
  >
    <Icon :name="iconName" :class="iconClass || 'size-7'" />
    <span class="font-mono text-xs uppercase tracking-widest opacity-80">{{ sku }}</span>
  </div>
</template>
