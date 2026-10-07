<script setup lang="ts">
import type { ZoneView } from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";

defineProps<{
  zone: ZoneView;
  cards: OrderCardProjection[];
  wide: boolean;
  fulfillment: string;
  exitFilterTabs: { value: string; label: string; icon: string }[];
  layoutMemory: string;
  layoutMemoryTitle: string;
  canCollapse: boolean;
  shortcut: string;
}>();

const emit = defineEmits<{
  collapse: [];
  updateFulfillment: [value: string | number];
}>();
</script>

<template>
  <div class="flex w-full min-w-max items-center gap-2" data-board-heading>
    <Icon :name="zone.icon" class="size-4 text-muted-foreground" />
    <h2 class="op-eyebrow">{{ zone.title }}</h2>
    <NuxtBadge
      color="neutral"
      variant="subtle"
      :label="
        wide
          ? `${cards.length} ${cards.length === 1 ? 'pronto ou quase' : 'prontos ou quase'}`
          : String(cards.length)
      "
    />
    <span
      v-if="wide"
      class="hidden items-center gap-1.5 op-micro text-muted-foreground lg:inline-flex"
      :title="layoutMemoryTitle"
      data-board-layout-memory
    >
      <Icon name="lucide:cloud-check" class="size-4" aria-hidden="true" />
      {{ layoutMemory }}
    </span>
    <span
      v-else
      class="hidden truncate op-micro text-muted-foreground sm:block"
      :title="zone.subtitle"
    >
      {{ zone.subtitle }}
    </span>

    <div class="ms-auto flex items-center gap-1.5">
      <NuxtTabs
        v-if="wide"
        :model-value="fulfillment"
        :items="exitFilterTabs"
        :content="false"
        aria-label="Filtrar a Saída"
        @update:model-value="emit('updateFulfillment', $event)"
      />
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
