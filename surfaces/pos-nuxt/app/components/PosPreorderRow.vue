<script setup lang="ts">
// Uma encomenda numa lista: o dia, a coluna da semana ou a busca. A linha
// inteira é o toque que abre o detalhe — não há botão dentro dela.
//
// O selo de situação usa a peça do kit (`toneBadge`), a mesma do detalhe e do
// Gestor; o saldo usa a apresentação única do "A receber" (`TO_RECEIVE_CLASS`).
import { toneBadge } from "../../../operator-kit/app/presentation/orderDetail";
import { fulfillmentIcon } from "~/presentation/orderTickets";
import { preorderDetailPath } from "~/presentation/preorderDetail";
import { TO_RECEIVE_CLASS, balanceStandsOut, customerLine, moneyLine, situationTone } from "~/presentation/preorders";
import type { PreorderCard } from "~/types/preorders";

const props = withDefaults(defineProps<{
  card: PreorderCard;
  /** Mostrar a data (na busca, onde os dias se misturam). */
  showDate?: boolean;
  /** O recorte da lista de onde a linha foi aberta: a volta do detalhe cai nele. */
  back?: string;
}>(), { showDate: false, back: "" });

const toneClass = computed(() => toneBadge(situationTone(props.card.situation)));
// O saldo a cobrar é o número que decide o gesto do balcão: ganha o peso do
// "A receber". Pago, na conta da casa ou a conferir seguem discretos.
const moneyClass = computed(() => (balanceStandsOut(props.card)
  ? TO_RECEIVE_CLASS
  : "text-xs tabular-nums text-muted-foreground"));
const detailLine = computed(() => {
  const parts = [props.card.ref, props.card.channel_label, props.card.fulfillment_label];
  if (props.showDate) parts.push(props.card.commitment_date_display);
  if (props.card.window_label) parts.push(props.card.window_label);
  return parts.filter(Boolean).join(" · ");
});
const printedLabel = computed(() => (props.card.ticket_printed ? "Via Pedido impressa" : ""));
</script>

<template>
  <NuxtLink
    :to="preorderDetailPath(card.ref, back)"
    class="flex min-h-11 items-start gap-3 rounded-md border border-border bg-card p-3 text-left transition hover:border-primary/50 hover:bg-accent hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    :data-preorder="card.ref"
  >
    <Icon
      :name="fulfillmentIcon(card.fulfillment_type)"
      class="mt-0.5 size-5 shrink-0 text-muted-foreground"
      :aria-label="card.fulfillment_label"
    />
    <div class="grid min-w-0 flex-1 gap-0.5">
      <p class="truncate text-sm font-medium" :title="customerLine(card)">{{ customerLine(card) }}</p>
      <p class="truncate text-xs text-muted-foreground" :title="detailLine">{{ detailLine }}</p>
      <p v-if="card.items_summary" class="truncate text-xs text-muted-foreground" :title="card.items_summary">{{ card.items_summary }}</p>
    </div>
    <div class="grid shrink-0 justify-items-end gap-1 text-right">
      <span class="flex items-center gap-1.5">
        <Icon
          v-if="card.ticket_printed"
          name="lucide:printer-check"
          class="size-4 text-muted-foreground"
          :aria-label="printedLabel"
          data-preorder-printed
        />
        <span class="rounded-md border px-1.5 py-0.5 text-xs font-medium" :class="toneClass" data-preorder-situation>
          {{ card.situation_label }}
        </span>
      </span>
      <span
        :class="moneyClass"
        :data-preorder-money="balanceStandsOut(card) ? 'to-receive' : 'settled'"
      >{{ moneyLine(card) }}</span>
    </div>
  </NuxtLink>
</template>
