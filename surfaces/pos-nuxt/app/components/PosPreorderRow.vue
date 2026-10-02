<script setup lang="ts">
// Uma encomenda numa lista: o dia, a coluna da semana ou a busca. A linha
// inteira é o toque que abre o detalhe; não há botão dentro dela.
//
// Uma forma só nos três lugares (brief do redesenho, 3.3), em duas linhas:
//
//   09:00    Ana Souza                           A receber R$ 48,00
//   [ícone]  NB-7 · WhatsApp · Retirada · 2 itens      Via impressa
//
// Na coluna estreita da semana o nome guarda pelo menos 7rem: o dinheiro quebra
// a linha antes de esmagar quem é. Três pilhas lado a lado (janela, quem,
// dinheiro), e não uma grade de duas linhas, para o dinheiro que quebra não
// afastar o nome da linha de baixo.
//
// - a janela primeiro, porque é a ordem em que o balcão trabalha;
// - o saldo na forma única do "A receber" (`TO_RECEIVE_CLASS`);
// - o selo de situação (a peça do kit, `toneBadge`) só quando diz o que o
//   dinheiro não diz: "Pronto", "Saiu para entrega", "Entregue";
// - "Via impressa" escrita, além do ícone.
import { toneBadge } from "../../../operator-kit/app/presentation/orderDetail";
import { fulfillmentIcon } from "~/presentation/orderTickets";
import { preorderDetailPath } from "~/presentation/preorderDetail";
import {
  PRINTED_LABEL,
  TO_RECEIVE_CLASS,
  balanceStandsOut,
  customerLine,
  moneyLine,
  moneyPieces,
  rowDetailLine,
  rowShowsSituation,
  rowWindow,
  situationTone,
} from "~/presentation/preorders";
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
const detailLine = computed(() => rowDetailLine(props.card, props.showDate));
</script>

<template>
  <NuxtLink
    :to="preorderDetailPath(card.ref, back)"
    class="flex min-h-11 items-start gap-3 rounded-md border border-border bg-card p-3 text-left transition hover:border-primary/50 hover:bg-accent hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    :data-preorder="card.ref"
  >
    <!-- A janela, e embaixo dela o recebimento. -->
    <span class="grid shrink-0 justify-items-start gap-1">
      <span
        class="tabular-nums"
        :class="card.window_start ? 'text-sm font-semibold' : 'pt-0.5 text-xs text-muted-foreground'"
        :title="card.window_label || undefined"
        data-preorder-window
      >{{ rowWindow(card) }}</span>
      <Icon
        :name="fulfillmentIcon(card.fulfillment_type)"
        class="size-4 text-muted-foreground"
        :aria-label="card.fulfillment_label"
      />
    </span>
    <!-- Quem, e embaixo o número, o canal, o recebimento e os itens. -->
    <span class="grid min-w-28 flex-1 basis-0 gap-0.5">
      <p class="truncate text-sm font-medium" :title="customerLine(card)">{{ customerLine(card) }}</p>
      <p class="text-xs text-muted-foreground">{{ detailLine }}</p>
    </span>
    <!-- O dinheiro, e embaixo o que ele não diz: o selo e a Via impressa. -->
    <span class="grid min-w-0 justify-items-end gap-1 text-right">
      <span
        :class="moneyClass"
        :data-preorder-money="balanceStandsOut(card) ? 'to-receive' : 'settled'"
      ><span
        v-for="(piece, index) in moneyPieces(moneyLine(card))"
        :key="index"
        :class="piece.amount ? 'whitespace-nowrap' : undefined"
      >{{ piece.text }}</span></span>
      <span
        v-if="rowShowsSituation(card.situation)"
        class="rounded-md border px-1.5 py-0.5 text-xs font-medium"
        :class="toneClass"
        data-preorder-situation
      >{{ card.situation_label }}</span>
      <span v-if="card.ticket_printed" class="inline-flex items-center gap-1 text-xs text-muted-foreground" data-preorder-printed>
        <Icon name="lucide:printer-check" class="size-3.5" aria-hidden="true" />
        {{ PRINTED_LABEL }}
      </span>
    </span>
  </NuxtLink>
</template>
