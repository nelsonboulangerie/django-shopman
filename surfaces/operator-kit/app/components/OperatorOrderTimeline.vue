<script setup lang="ts">
// O histórico do pedido, com o comentar (peça do `OperatorOrderDetail`). O comentar só
// aparece quando o servidor oferece a ação `comment` neste contexto. `title` muda com o
// desenho: "Histórico" na coluna única, "Linha do tempo" no detalhe em duas colunas
// (prévia v3 `depois-gestor-detalhe`).
import { computed } from "vue";

import { canComment as canCommentOn } from "../presentation/orderDetail";
import type { OperatorOrderDetail } from "../types/orderDetail";

const props = withDefaults(defineProps<{
  order: OperatorOrderDetail;
  busy?: boolean;
  title?: string;
  /** Sem o campo de comentar (o resumo de quem está fora da loja). */
  readOnly?: boolean;
}>(), { busy: false, title: "Histórico", readOnly: false });

const emit = defineEmits<{ comment: [note: string] }>();
const comment = defineModel<string>("comment", { default: "" });
const commentAllowed = computed(() => !props.readOnly && canCommentOn(props.order));

function submitComment() {
  const note = comment.value.trim();
  if (!note || props.busy) return;
  emit("comment", note);
}
</script>

<template>
  <section class="flex flex-col gap-2 rounded-lg border bg-card p-4" data-order-timeline>
    <h2 class="text-sm font-bold uppercase tracking-wide">{{ title }}</h2>
    <ol v-if="order.timeline.length" class="flex flex-col gap-2.5">
      <li v-for="(ev, i) in order.timeline" :key="i" class="flex gap-3 text-sm">
        <span class="mt-1 size-2 shrink-0 rounded-full" :class="ev.event_type === 'operator_comment' ? 'bg-primary' : 'bg-muted-foreground/40'" />
        <div class="min-w-0">
          <p class="font-medium">{{ ev.label }}</p>
          <p class="text-xs text-muted-foreground">{{ ev.timestamp_display }}<template v-if="ev.actor"> · {{ ev.actor }}</template><template v-if="ev.detail"> · {{ ev.detail }}</template></p>
        </div>
      </li>
    </ol>
    <p v-else class="text-sm text-muted-foreground" data-order-timeline-empty>Ainda não há nada no histórico deste pedido.</p>

    <!-- comentar: só quando o servidor oferece a ação neste contexto -->
    <div v-if="commentAllowed" class="flex items-start gap-2 border-t pt-3" data-order-comment>
      <textarea
        v-model="comment"
        rows="1"
        placeholder="Comentar no histórico…"
        class="min-h-control flex-1 resize-y rounded-md border bg-background p-2 text-sm outline-none focus:ring-1 focus:ring-ring"
        aria-label="Comentar no histórico"
        @keydown.enter.meta.prevent="submitComment"
      />
      <button
        type="button"
        :disabled="!comment.trim() || busy"
        class="inline-flex min-h-action shrink-0 items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        data-order-comment-submit
        @click="submitComment"
      >
        <Icon name="lucide:message-square-plus" class="size-4" /> Comentar
      </button>
    </div>
  </section>
</template>
