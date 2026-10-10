<script setup lang="ts">
// Uma encomenda numa lista: o dia, a coluna da semana ou a busca. A linha
// inteira é o toque que abre o detalhe; não há botão dentro dela.
//
// Uma forma só nos três lugares (brief do redesenho, 3.3), em duas linhas:
//
//   09:00    Ana Souza                           A receber R$ 48,00
//   [ícone]  NB-7 · WhatsApp · Retirada · 2 itens      Via impressa
//
// Na coluna estreita da semana o nome guarda pelo menos 5rem (7rem antes do botão
// "Mudar de dia" ao lado): o dinheiro quebra
// a linha antes de esmagar quem é. Texto da casa nunca se corta (regra do kit): o
// nome, o recebimento e os itens quebram linha. Três pilhas lado a lado (janela, quem,
// dinheiro), e não uma grade de duas linhas, para o dinheiro que quebra não
// afastar o nome da linha de baixo.
//
// - a janela primeiro, porque é a ordem em que o balcão trabalha;
// - o saldo na forma única do "A receber" (`TO_RECEIVE_CLASS`);
// - o selo de situação (a peça do kit, `toneBadge`) só quando diz o que o
//   dinheiro não diz: "Pronto", "Saiu para entrega", "Entregue";
// - "Via impressa" escrita, além do ícone.
//
// Na semana o card também se ARRASTA para outro dia (`movable`): o invólucro é que
// se pega, e o link não (senão o navegador arrastaria o endereço). O gesto
// equivalente por teclado e toque mora no slot `aside`, ao lado do link e fora
// dele (botão dentro de link não é HTML válido nem alvo de toque honesto).
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
  phoneCardPills,
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
  /** O card se arrasta para outro dia (só na semana, e só o que pode mudar de data). */
  movable?: boolean;
}>(), { showDate: false, back: "", movable: false });

const slots = useSlots();

const toneClass = computed(() => toneBadge(situationTone(props.card.situation)));
// O saldo a cobrar é o número que decide o gesto do balcão: ganha o peso do
// "A receber". Pago, na conta da casa ou a conferir seguem discretos.
const moneyClass = computed(() => (balanceStandsOut(props.card)
  ? TO_RECEIVE_CLASS
  : "text-xs tabular-nums text-muted-foreground"));
const detailLine = computed(() => rowDetailLine(props.card, props.showDate));
const pills = computed(() => phoneCardPills(props.card));
</script>

<template>
  <div
    class="flex min-w-0 items-stretch rounded-md bg-elevated/50 transition hover:bg-elevated"
    :draggable="movable ? 'true' : undefined"
    :data-preorder-card="card.ref"
    :data-preorder-movable="movable ? '' : undefined"
  >
    <NuxtLink
      :to="preorderDetailPath(card.ref, back)"
      class="flex min-h-8 min-w-0 flex-1 items-start gap-3 p-3 text-left focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
      :class="slots.aside ? 'rounded-l-md' : 'rounded-md'"
      :draggable="movable ? 'false' : undefined"
      :data-preorder="card.ref"
    >
      <!-- CELULAR (v3 `depois-pdv-celular` 3): o cartão com a hora numa caixa, o
           cliente e o total, o recebimento com os itens, e as duas pílulas. -->
      <span class="grid size-16 shrink-0 place-items-center content-center rounded-md bg-secondary text-center md:hidden" data-preorder-phone-time>
        <span v-if="card.window_start" class="text-lg leading-none font-semibold tnum">{{ card.window_start }}</span>
        <span v-else class="op-micro leading-tight font-semibold">a combinar</span>
        <span class="mt-1 op-micro text-muted-foreground">{{ card.commitment_date_display }}</span>
      </span>
      <span class="grid min-w-0 flex-1 gap-1 md:hidden" data-preorder-phone>
        <span class="flex items-baseline gap-2">
          <span class="min-w-0 flex-1 break-words op-label font-semibold" data-preorder-name>{{ card.customer_name || card.ref }}</span>
          <span class="shrink-0 op-label font-semibold tnum">{{ card.total_display }}</span>
        </span>
        <span class="flex min-w-0 items-start gap-1 op-micro text-muted-foreground">
          <Icon :name="fulfillmentIcon(card.fulfillment_type)" class="size-3.5 shrink-0" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ [card.fulfillment_label, card.items_summary].filter(Boolean).join(" · ") }}</span>
        </span>
        <span class="flex flex-wrap gap-1">
          <span
            v-for="pill in pills"
            :key="pill.label"
            class="inline-flex h-6 items-center gap-1 rounded-full px-2 op-micro font-semibold"
            :class="toneBadge(pill.tone)"
          ><span class="size-1.5 rounded-full bg-current" aria-hidden="true" />{{ pill.label }}</span>
        </span>
      </span>
      <!-- A janela, e embaixo dela o recebimento. -->
      <span class="grid shrink-0 justify-items-start gap-1 max-md:hidden">
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
      <span class="grid min-w-20 flex-1 basis-0 gap-0.5 max-md:hidden">
        <p class="break-words text-sm font-medium" data-preorder-name>{{ customerLine(card) }}</p>
        <p class="text-xs text-muted-foreground">{{ detailLine }}</p>
      </span>
      <!-- O dinheiro, e embaixo o que ele não diz: o selo e a Via impressa. -->
      <span class="grid min-w-0 justify-items-end gap-1 text-right max-md:hidden">
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
    <div v-if="slots.aside" class="flex shrink-0 items-start max-md:hidden">
      <slot name="aside" />
    </div>
  </div>
</template>
