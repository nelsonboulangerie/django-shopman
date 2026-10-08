<script setup lang="ts">
// O histórico do pedido, com o comentar (peça do `OperatorOrderDetail`). O comentar só
// aparece quando o servidor oferece a ação `comment` neste contexto. `title` muda com o
// desenho: "Histórico" na coluna única, "Linha do tempo" no detalhe em duas colunas
// (prévia v3 `depois-gestor-detalhe`).
import { computed } from "vue";

import { canComment as canCommentOn } from "../presentation/orderDetail";
import type { OperatorOrderDetail } from "../types/orderDetail";

const props = withDefaults(
  defineProps<{
    order: OperatorOrderDetail;
    busy?: boolean;
    title?: string;
    /** Sem o campo de comentar (o resumo de quem está fora da loja). */
    readOnly?: boolean;
  }>(),
  { busy: false, title: "Histórico", readOnly: false },
);

const emit = defineEmits<{ comment: [note: string] }>();
const comment = defineModel<string>("comment", { default: "" });
const commentAllowed = computed(
  () => !props.readOnly && canCommentOn(props.order),
);

function submitComment() {
  const note = comment.value.trim();
  if (!note || props.busy) return;
  emit("comment", note);
}
</script>

<template>
  <NuxtCard data-order-timeline>
    <template #header
      ><h2 class="op-title">{{ title }}</h2></template
    >
    <NuxtTimeline
      v-if="order.timeline.length"
      :items="
        order.timeline.map((event) => ({
          title: event.label,
          description: [event.timestamp_display, event.actor, event.detail]
            .filter(Boolean)
            .join(' · '),
          icon:
            event.event_type === 'operator_comment'
              ? 'i-lucide-message-square'
              : 'i-lucide-circle-check',
        }))
      "
    />
    <NuxtEmpty
      v-else
      icon="i-lucide-history"
      title="Ainda não há nada no histórico deste pedido."
      data-order-timeline-empty
    />

    <template v-if="commentAllowed" #footer>
      <!-- Comentar é a ação da linha do tempo; o footer oficial separa a entrada
           do histórico já confirmado sem inventar borda ou padding local. -->
      <div class="flex flex-col gap-2">
        <NuxtFormField label="Comentar no histórico" data-order-comment>
          <NuxtTextarea
            v-model="comment"
            class="w-full"
            :rows="2"
            placeholder="Escreva uma atualização…"
            autoresize
            @keydown.meta.enter.prevent="submitComment"
          />
        </NuxtFormField>
        <NuxtButton
          class="self-end"
          :disabled="!comment.trim() || busy"
          :loading="busy"
          icon="i-lucide-message-square-plus"
          label="Comentar"
          color="primary"
          variant="solid"
          data-order-comment-submit
          @click="submitComment"
        />
      </div>
    </template>
  </NuxtCard>
</template>
