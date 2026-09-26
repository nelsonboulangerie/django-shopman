<script setup lang="ts">
// Uma encomenda numa lista (busca, hoje) ou numa coluna da grade semanal. A
// linha inteira é o toque que abre o detalhe — não há botão dentro dela.
//
// `compact` é a coluna da grade: estreita, sem o canal e sem o resumo dos
// itens, porque sete colunas lado a lado não cabem numa linha de pedido
// inteira. O que fica é o que responde "quanto temos para sábado": quem, que
// horas, a situação e o dinheiro.
import { fulfillmentIcon } from "~/presentation/orderTickets";
import { balanceStandsOut, customerLine, moneyLine, situationTone } from "~/presentation/preorders";
import type { PreorderCard } from "~/types/preorders";

const props = withDefaults(defineProps<{
  card: PreorderCard;
  compact?: boolean;
  /** Mostrar a data (na busca, onde os dias se misturam). */
  showDate?: boolean;
}>(), { compact: false, showDate: false });

const TONE_CLASS: Record<string, string> = {
  warning: "border-warning/40 bg-warning/10 text-warning",
  success: "border-success/40 bg-success/10 text-success",
  info: "border-info/40 bg-info/10 text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

const toneClass = computed(() => TONE_CLASS[situationTone(props.card.situation)]);
// O saldo a cobrar é o número que decide o gesto do balcão: ganha peso e cor de
// texto cheia. Pago, na conta da casa ou a conferir seguem discretos.
const moneyClass = computed(() => (balanceStandsOut(props.card)
  ? "text-sm font-semibold text-foreground"
  : "text-xs text-muted-foreground"));
const detailLine = computed(() => {
  const parts = [props.card.ref];
  if (!props.compact) parts.push(props.card.channel_label);
  parts.push(props.card.fulfillment_label);
  if (props.showDate) parts.push(props.card.commitment_date_display);
  if (props.card.window_label) parts.push(props.card.window_label);
  return parts.filter(Boolean).join(" · ");
});
</script>

<template>
  <NuxtLink
    :to="`/preorders/${encodeURIComponent(card.ref)}`"
    class="flex gap-3 rounded-md border border-border bg-card text-left transition hover:border-primary/40 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    :class="compact ? 'flex-col p-2' : 'items-start p-3'"
    :data-preorder="card.ref"
  >
    <Icon
      v-if="!compact"
      :name="fulfillmentIcon(card.fulfillment_type)"
      class="mt-0.5 size-5 shrink-0 text-muted-foreground"
      :aria-label="card.fulfillment_label"
    />
    <div class="grid min-w-0 flex-1 gap-0.5">
      <p class="truncate text-sm font-medium" :title="customerLine(card)">{{ customerLine(card) }}</p>
      <p class="truncate text-xs text-muted-foreground" :title="detailLine">{{ detailLine }}</p>
      <p v-if="!compact && card.items_summary" class="truncate text-xs text-muted-foreground">{{ card.items_summary }}</p>
    </div>
    <div class="grid shrink-0 gap-1" :class="compact ? 'justify-items-start' : 'justify-items-end text-right'">
      <span class="rounded-md border px-1.5 py-0.5 text-xs font-medium" :class="toneClass" data-preorder-situation>
        {{ card.situation_label }}
      </span>
      <span
        class="tabular-nums"
        :class="moneyClass"
        :data-preorder-money="balanceStandsOut(card) ? 'to-receive' : 'settled'"
      >{{ moneyLine(card) }}</span>
    </div>
  </NuxtLink>
</template>
