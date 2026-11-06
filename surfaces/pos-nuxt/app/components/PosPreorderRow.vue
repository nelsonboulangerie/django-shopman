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
// - "Via impressa" escrita, além do ícone;
// - na entrega da casa, a corrida do entregador numa linha ("Entregador não
//   chamado", "Procurando entregador", "Não atendida"): o chamar mora no detalhe.
//
// Na semana o card também se ARRASTA para outro dia (`movable`): o invólucro é que
// se pega, e o link não (senão o navegador arrastaria o endereço). O gesto
// equivalente por teclado e toque mora no slot `aside`, ao lado do link e fora
// dele (botão dentro de link não é HTML válido nem alvo de toque honesto).
import { toneBadge } from "../../../operator-kit/app/presentation/orderDetail";
import { fulfillmentIcon } from "~/presentation/orderTickets";
import { COURIER_TEXT, courierRowLine } from "~/presentation/courier";
import { preorderDetailPath } from "~/presentation/preorderDetail";
import {
  PRINTED_LABEL,
  TO_RECEIVE_CLASS,
  balanceStandsOut,
  moneyBadge,
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
  /**
   * `lines`: a linha da semana (dono, 03/11/2026), sem caixa, separada por fio, em duas
   * linhas na largura toda: hora · quem · [recebimento] [canal] ...... dinheiro, e embaixo
   * o que foi pedido e o número ...... a situação ou a Via impressa.
   */
  layout?: "" | "lines";
}>(), { showDate: false, back: "", movable: false, layout: "" });

const slots = useSlots();

const toneClass = computed(() => toneBadge(situationTone(props.card.situation)));
// O saldo a cobrar é o número que decide o gesto do balcão: ganha o peso do
// "A receber". Pago, na conta da casa ou a conferir seguem discretos.
const moneyClass = computed(() => (balanceStandsOut(props.card)
  ? TO_RECEIVE_CLASS
  : "text-xs tabular-nums text-muted-foreground"));
const detailLine = computed(() => rowDetailLine(props.card, props.showDate));
const pills = computed(() => phoneCardPills(props.card));
// A corrida do entregador (TaOn), na encomenda de entrega da casa: a frase e o tom
// são do servidor; o texto na cor do tom (o neutro, discreto).
const courierLine = computed(() => courierRowLine(props.card));
const courierClass = computed(() => COURIER_TEXT[courierLine.value?.tone ?? "neutral"]);
// A linha da semana: o dinheiro em valor + selo semântico, e os selos de quem.
const money = computed(() => moneyBadge(props.card));
const situationColor = computed(() => situationTone(props.card.situation));
</script>

<template>
  <div
    class="@container flex min-w-0 items-stretch transition"
    :class="layout ? 'hover:bg-elevated/60' : 'rounded-md bg-elevated/50 hover:bg-elevated'"
    :draggable="movable ? 'true' : undefined"
    :data-preorder-card="card.ref"
    :data-preorder-movable="movable ? '' : undefined"
  >
    <NuxtLink
      :to="preorderDetailPath(card.ref, back)"
      class="grid min-h-8 min-w-0 flex-1 grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-1 text-left focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
      :class="[
        layout === 'lines'
          ? 'px-3 py-2 @md:grid-cols-[minmax(4.5rem,auto)_minmax(0,1fr)_auto] md:gap-y-1'
          : 'p-3 md:grid-cols-[auto_minmax(5rem,1fr)_auto]',
        layout ? '' : (slots.aside ? 'rounded-l-md' : 'rounded-md'),
      ]"
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
        <span
          v-if="courierLine"
          class="flex min-w-0 items-center gap-1 op-micro font-medium"
          :class="courierClass"
          data-preorder-courier
        >
          <Icon name="lucide:bike" class="size-3.5 shrink-0" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ courierLine.label }}</span>
        </span>
        <span class="flex flex-wrap gap-1">
          <NuxtBadge
            v-for="pill in pills"
            :key="pill.label"
            :color="pill.tone"
            :label="pill.label"
            size="sm"
          />
        </span>
      </span>
      <!-- A LINHA DA SEMANA (`layout="lines"`). Em cima: a hora, quem e os selos de quem
           (recebimento e canal), o valor com o selo do estado. Os selos são UM bloco: se
           não cabem todos ao lado do nome, descem todos juntos (dono, 03/11/2026).
           Embaixo: o que foi pedido e o número; a situação ou a Via impressa.
           As três colunas valem pela largura da LINHA, não da janela (`@container`): na
           coluna do dia aberta no tablet em pé (uns 270 px) o valor e o selo tiravam toda
           a largura do nome, que quebrava letra a letra. Estreita, a linha tem duas
           colunas: a hora, e ao lado dela quem, o valor, o pedido e a situação. -->
      <template v-if="layout === 'lines'">
        <!-- A hora numa linha só: "A combinar" não quebra nem invade a coluna do nome. -->
        <span
          class="row-span-2 whitespace-nowrap pt-px tabular-nums max-md:hidden @max-md:row-span-4"
          :class="card.window_start ? 'text-sm font-semibold' : 'text-xs text-muted'"
          data-preorder-window
        >{{ rowWindow(card) }}</span>
        <span class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 max-md:hidden">
          <span class="break-words text-sm font-medium" data-preorder-name>{{ customerLine(card) }}</span>
          <span class="inline-flex shrink-0 items-center gap-1" data-preorder-badges>
            <NuxtBadge
              color="neutral"
              :icon="fulfillmentIcon(card.fulfillment_type).replace('lucide:', 'i-lucide-')"
              :label="card.fulfillment_label"
              size="sm"
              data-preorder-fulfillment
            />
            <NuxtBadge v-if="card.channel_label" color="neutral" :label="card.channel_label" size="sm" data-preorder-channel />
          </span>
        </span>
        <span class="flex items-center justify-end gap-2 max-md:hidden @max-md:justify-start">
          <span class="text-sm font-semibold tabular-nums text-highlighted" :data-preorder-money="balanceStandsOut(card) ? 'to-receive' : 'settled'">{{ money.amount }}</span>
          <NuxtBadge :color="money.tone" :label="money.label" size="sm" data-preorder-money-badge />
        </span>
        <span class="min-w-0 break-words text-xs text-muted max-md:hidden">{{ [card.items_summary, card.ref].filter(Boolean).join(" · ") }}</span>
        <span class="flex items-center justify-end gap-2 text-xs text-muted max-md:hidden @max-md:justify-start">
          <span v-if="money.of" class="tabular-nums">{{ money.of }}</span>
          <NuxtBadge v-if="rowShowsSituation(card.situation)" :color="situationColor" :label="card.situation_label" size="sm" data-preorder-situation />
          <span v-else-if="card.ticket_printed" class="inline-flex items-center gap-1" data-preorder-printed>
            <Icon name="lucide:printer-check" class="size-3.5" aria-hidden="true" />{{ PRINTED_LABEL }}
          </span>
        </span>
      </template>
      <template v-else>
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
      </template>
      <!-- A corrida do entregador numa linha inteira, sob quem e o dinheiro: a frase
           não se espreme na coluna do nome. Na linha da semana estreita (duas colunas)
           ela ocupa só a coluna do texto: `col-span-2` ali criava uma terceira coluna. -->
      <p
        v-if="courierLine"
        class="col-start-2 flex items-center gap-1 text-xs font-medium max-md:hidden"
        :class="[layout === 'lines' ? '@md:col-span-2' : 'col-span-2', courierClass]"
        data-preorder-courier
      >
        <Icon name="lucide:bike" class="size-3.5 shrink-0" aria-hidden="true" />
        <span class="min-w-0 break-words">{{ courierLine.label }}</span>
      </p>
    </NuxtLink>
    <div v-if="slots.aside" class="flex shrink-0 items-start max-md:hidden">
      <slot name="aside" />
    </div>
  </div>
</template>
