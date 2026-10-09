<script setup lang="ts">
// Os recortes ativos como chips removíveis (as "facetas" do Odoo). Favorito aplicado é
// UM chip com a estrela. Na mesa os chips seguem na mesma linha da toolbar; no celular
// descem para uma faixa própria que rola na horizontal, logo abaixo da toolbar.
import type { Fase2Facet } from "../data/fase2Filters";

withDefaults(defineProps<{ facets: readonly Fase2Facet[]; scroll?: boolean }>(), { scroll: false });
const emit = defineEmits<{ remove: [id: string] }>();
</script>

<template>
  <ul
    v-if="facets.length"
    class="flex min-w-0 items-center gap-2"
    :class="scroll ? 'overflow-x-auto' : 'flex-wrap'"
    aria-label="Recortes ativos"
    data-fase2-facets
  >
    <li v-for="facet in facets" :key="facet.id" class="shrink-0">
      <NuxtButton
        :label="facet.label"
        :icon="facet.favorite ? 'i-lucide-star' : undefined"
        trailing-icon="i-lucide-x"
        color="neutral"
        variant="outline"
        :aria-label="`Tirar o recorte ${facet.label}`"
        @click="emit('remove', facet.id)"
      />
    </li>
  </ul>
</template>
