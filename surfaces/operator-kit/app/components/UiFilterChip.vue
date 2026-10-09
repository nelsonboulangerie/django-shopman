<script setup lang="ts">
// Compatibilidade temporária para apps ainda não migrados. O Gestor usa NuxtTabs
// diretamente. Não há receita visual local: só props públicas do Nuxt UI.
//
// ⚠️ `min-h-control` (44 px; 48 px em tablet touch) é alvo de toque, não estética:
// a pílula vive no balcão do PDV (Encomendas), no KDS e na Produção. A pilha do
// Gestor tinha deixado o `md` oficial (32 px) e o PDV perdeu o alvo sem pedir.
// A contagem é outra grandeza: à parte do rótulo, no chip de contagem da suíte
// (`OperatorCountChip`: círculo âmbar na ponta direita, no centro vertical; zero não
// aparece).
defineProps<{
  active?: boolean;
  count?: number | null;
}>();
</script>

<template>
  <NuxtButton
    type="button"
    class="min-h-control"
    :color="active ? 'primary' : 'neutral'"
    :variant="active ? 'soft' : 'outline'"
  >
    <slot name="icon" />
    <slot />
    <OperatorCountChip :count="count" />
  </NuxtButton>
</template>
