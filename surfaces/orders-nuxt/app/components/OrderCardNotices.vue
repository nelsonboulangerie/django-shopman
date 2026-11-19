<script setup lang="ts">
// Os avisos do cartão do pedido (dono, 07/10/2026): a pílula com a cor e o nome; o
// texto e o gesto no Popover. Um lugar só para o cartão inteiro e o enxuto do Painel.
//
// A pílula diz o fato, não uma pergunta (WP-G06): o bloqueio aparece pelo nome ("Pix
// expirado"), e o botão que só abre o pedido diz que abre (`cardNoticeView`).
import { computed } from "vue";

import type { CardNotice } from "./OrderCard.vue";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";
import { cardNoticeView } from "~/presentation/cardBlocks";

const props = defineProps<{ notices: CardNotice[] }>();
const shown = computed(() => props.notices.map(cardNoticeView));
</script>

<template>
  <div v-if="shown.length" class="flex flex-wrap gap-1.5" data-card-notices>
    <NuxtPopover
      v-for="notice in shown"
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
