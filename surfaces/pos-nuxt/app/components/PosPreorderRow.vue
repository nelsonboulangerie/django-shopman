<script setup lang="ts">
// Uma encomenda numa lista (o dia, a busca) ou numa coluna da grade semanal. A
// linha inteira é o toque que abre o detalhe — não há botão dentro dela.
//
// `compact` é a coluna da grade: estreita, sem o canal, sem o resumo dos itens
// e sem o selo de situação, porque sete colunas lado a lado não cabem numa
// linha de pedido inteira. O que fica é o que responde "quanto temos para
// sábado": que horas, quem, retirada ou entrega, o saldo (ou "pago") e se a Via
// Pedido já saiu.
import { fulfillmentIcon } from "~/presentation/orderTickets";
import { preorderDetailPath } from "~/presentation/preorderDetail";
import { balanceStandsOut, compactMoneyLine, customerLine, moneyLine, situationTone } from "~/presentation/preorders";
import type { PreorderCard } from "~/types/preorders";

const props = withDefaults(defineProps<{
  card: PreorderCard;
  compact?: boolean;
  /** Mostrar a data (na busca, onde os dias se misturam). */
  showDate?: boolean;
  /** O recorte da lista de onde a linha foi aberta: a volta do detalhe cai nele. */
  back?: string;
}>(), { compact: false, showDate: false, back: "" });

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
    class="flex min-h-11 rounded-md border border-border bg-card text-left transition hover:border-primary/50 hover:bg-accent hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    :class="compact ? 'flex-col gap-1 p-2.5' : 'items-start gap-3 p-3'"
    :data-preorder="card.ref"
  >
    <!-- COLUNA DA GRADE: janela · quem · recebimento · dinheiro · via. -->
    <template v-if="compact">
      <span class="flex items-center gap-1 text-xs text-muted-foreground">
        <Icon :name="fulfillmentIcon(card.fulfillment_type)" class="size-3.5 shrink-0" :aria-label="card.fulfillment_label" />
        <span class="min-w-0 flex-1 break-words">{{ card.window_start || "Sem horário" }}</span>
        <Icon
          v-if="card.ticket_printed"
          name="lucide:printer-check"
          class="size-3.5 shrink-0"
          :aria-label="printedLabel"
          data-preorder-printed
        />
      </span>
      <span class="truncate text-sm font-medium" :title="customerLine(card)">{{ customerLine(card) }}</span>
      <span
        class="tabular-nums"
        :class="balanceStandsOut(card) ? 'text-sm font-semibold text-foreground' : 'text-xs text-muted-foreground'"
        :data-preorder-money="balanceStandsOut(card) ? 'to-receive' : 'settled'"
      >{{ compactMoneyLine(card) }}</span>
    </template>

    <!-- LINHA INTEIRA: o dia e a busca. -->
    <template v-else>
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
          class="tabular-nums"
          :class="moneyClass"
          :data-preorder-money="balanceStandsOut(card) ? 'to-receive' : 'settled'"
        >{{ moneyLine(card) }}</span>
      </div>
    </template>
  </NuxtLink>
</template>
