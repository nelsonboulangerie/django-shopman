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
  <div class="flex w-full min-w-max items-center gap-2" data-board-heading>
    <Icon :name="zone.icon" class="size-4 text-muted-foreground" />
    <h2 class="op-eyebrow">{{ zone.title }}</h2>
    <NuxtBadge color="neutral" variant="subtle" :label="String(cards.length)" />
    <span
      class="hidden truncate op-micro text-muted-foreground sm:block"
      :title="zone.subtitle"
    >
      {{ zone.subtitle }}
    </span>

    <div class="ms-auto flex items-center">
      <NuxtButton
        v-if="canCollapse"
        icon="i-lucide-panel-left-close"
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
