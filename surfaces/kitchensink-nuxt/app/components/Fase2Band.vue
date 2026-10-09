<script setup lang="ts">
// Uma faixa da maquete com o nome do papel dela (a regra: uma barra, um papel). O
// nome fica numa linha própria, acima da faixa, para não cobrir nenhum controle.
withDefaults(defineProps<{ role: string; grow?: boolean; tone?: "neutral" | "primary" }>(), {
  grow: false,
  tone: "neutral",
});
</script>

<template>
  <div
    class="border-b border-dashed border-default last:border-b-0"
    :class="grow ? 'flex-1' : ''"
    :data-fase2-band="role"
  >
    <div class="px-2 pt-1.5">
      <NuxtBadge :color="tone" :label="role" size="sm" />
    </div>
    <slot />
  </div>
</template>
