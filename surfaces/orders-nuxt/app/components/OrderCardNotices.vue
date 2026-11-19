<script setup lang="ts">
// Os avisos do cartão do pedido (dono, 07/10/2026): a pílula com a cor e o nome; o
// texto e o gesto no Popover. Um lugar só para o cartão inteiro e o enxuto do Painel.
import type { CardNotice } from "./OrderCard.vue";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

defineProps<{ notices: CardNotice[] }>();
</script>

<template>
  <div v-if="notices.length" class="flex flex-wrap gap-1.5" data-card-notices>
    <NuxtPopover
      v-for="notice in notices"
      :key="notice.key"
      :content="{ side: 'bottom', align: 'start' }"
    >
      <NuxtButton
        :color="notice.color"
        variant="soft"
        :icon="notice.icon"
        :label="notice.label"
        :data-card-notice="notice.key"
      />
      <template #content>
        <NuxtAlert
          class="max-w-80"
          :color="notice.color"
          variant="subtle"
          :icon="notice.icon"
          :title="notice.title"
          :description="notice.description"
          :actions="alertActions(notice.color, notice.actions ?? [])"
          v-bind="notice.attrs"
        />
      </template>
    </NuxtPopover>
  </div>
</template>
