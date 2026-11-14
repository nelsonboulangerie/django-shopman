<script setup lang="ts">
import type { ZoneView } from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";

defineProps<{
  zone: ZoneView;
  cards: OrderCardProjection[];
  canCollapse: boolean;
  shortcut: string;
}>();

const emit = defineEmits<{
  collapse: [];
}>();
</script>

<template>
  <!-- Minimalista (dono, 13/11/2026): o nome, o número e, no fim, o gesto da coluna e
       o recolher. O que a coluna guarda vai no título do nome, não numa segunda frase. -->
  <div class="flex w-full min-w-max items-center gap-2" data-board-heading>
    <h2 class="font-semibold text-highlighted" :title="zone.subtitle">
      {{ zone.title }}
    </h2>
    <span
      class="rounded-full bg-default px-2 op-micro font-semibold tnum text-highlighted"
      data-board-count
      >{{ cards.length }}</span
    >
    <div class="ms-auto flex items-center gap-1">
      <!-- O gesto da coluna inteira (em Prontos, "Juntar entregas"), antes do recolher. -->
      <slot name="actions" />
      <NuxtButton
        v-if="canCollapse"
        icon="i-lucide-chevrons-left"
        color="neutral"
        variant="ghost"
        square
        :aria-label="`Recolher a coluna ${zone.title} (atalho: ${shortcut})`"
        data-board-collapse
        @click="emit('collapse')"
      />
    </div>
  </div>
</template>
