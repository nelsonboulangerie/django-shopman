<script setup lang="ts">
// "Ver lotes e vendas" (prévia `bi-sobra4.html`, pino 7): aprofundar sem trocar de tela.
// Os lotes do dia (o registro de onde o "fez" saiu, cada um leva ao Fechamento da
// Produção daquele dia, e o lote que o plano tinha e não fechou), as vendas por hora
// (cheio = vendido; tracejado = a estimativa depois que acabou) e o que aconteceu
// depois: quando os canais tiraram o produto do ar, quantos pediram "Me avise", e os
// caminhos ao registro (os pedidos do dia no Gestor, os dias da comparação).
import type { BIOverShortRow } from "~/types/bi";
import { formatQty, shortDate } from "~/presentation/bi";
import {
  clientCount,
  formatCostWhole,
  historyDaysLabel,
  historyText,
  inTypical,
  lotsLine,
  ordersLinkLabel,
  unavailableText,
  verdictMeta,
} from "~/presentation/overShort";

const props = defineProps<{
  row: BIOverShortRow;
  day: string;
  compare: string;
  /** Link do Fechamento da Produção daquele dia (os lotes moram lá). */
  closeUrl: string;
  /** Base do Gestor: "Abrir os N pedidos" abre o Histórico daquele dia, só com o produto. */
  ordersUrl: string;
}>();

const route = useRoute();
const { attrsFor } = useOperatorAppLink();
const closeLink = computed(() => attrsFor(props.closeUrl));
const ordersHref = computed(() =>
  props.ordersUrl && props.row.orders
    ? `${props.ordersUrl}history?period=custom&from=${props.day}&to=${props.day}&sku=${encodeURIComponent(props.row.sku)}`
    : "",
);
const ordersLink = computed(() => attrsFor(ordersHref.value));
const showHistory = ref(false);

const hourMax = computed(() =>
  Math.max(1, ...props.row.sales_by_hour.map((hour) => Number(hour.sold) + Number(hour.estimated_lost))),
);
const barHeight = (value: number) => `${Math.max(value > 0 ? 6 : 0, (value / hourMax.value) * 64)}px`;

const capitalize = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
const hasEstimate = computed(() => props.row.sales_by_hour.some((hour) => Number(hour.estimated_lost) > 0));
const demandEstimate = computed(() => Number(props.row.sold) + Number(props.row.lost_estimate || 0));
const missingLot = computed(() => props.row.planned_lots > props.row.lots.length);
const historyEntries = computed(() =>
  props.row.history_days.map((iso, index) => ({ iso, verdict: props.row.history[index] ?? "right" })),
);
</script>

<template>
  <div class="grid gap-5 border-b border-border bg-primary/5 px-4 py-3 lg:grid-cols-[1.1fr_1fr_1.25fr]" data-over-short-detail>
    <div>
      <p class="mb-1.5 op-eyebrow text-muted-foreground">Lotes do dia</p>
      <a
        v-for="(lot, index) in row.lots"
        :key="lot.ref"
        :href="closeUrl"
        :target="closeLink.target"
        :rel="closeLink.rel"
        class="flex min-h-control items-center gap-2 op-label"
        :class="index ? 'border-t border-border' : ''"
        :aria-label="`Lote ${lot.ref}, ${formatQty(lot.qty)} unidades: abrir o Fechamento da Produção`"
      >
        <span class="font-mono text-primary underline underline-offset-2">{{ lot.ref }}</span>
        <span v-if="lot.finished_at" class="tnum text-muted-foreground">saiu {{ lot.finished_at }}</span>
        <span class="ml-auto tnum font-semibold">{{ formatQty(lot.qty) }} un.</span>
        <Icon name="lucide:arrow-up-right" class="size-3.5 text-muted-foreground" aria-hidden="true" />
      </a>
      <p class="mt-1 op-micro" :class="missingLot ? 'font-medium text-foreground' : 'text-muted-foreground'" data-over-short-lots-line>
        {{ lotsLine(row) }}
      </p>
    </div>

    <div>
      <p class="mb-1.5 op-eyebrow text-muted-foreground">Vendas por hora</p>
      <div v-if="row.sales_by_hour.length" class="flex h-[86px] items-end gap-1.5 overflow-x-auto no-scrollbar" role="img" :aria-label="`Vendas por hora de ${row.name}`">
        <div v-for="hour in row.sales_by_hour" :key="hour.hour" class="flex shrink-0 flex-col items-center gap-1">
          <div class="flex w-6 flex-col justify-end">
            <div
              v-if="Number(hour.estimated_lost) > 0"
              class="w-6 rounded-t-sm border border-dashed border-destructive/60 bg-destructive/10"
              :style="{ height: barHeight(Number(hour.estimated_lost)) }"
              :title="`${hour.hour}h: ~${formatQty(hour.estimated_lost)} perdidas (est.)`"
            />
            <div
              v-if="Number(hour.sold) > 0"
              class="w-6 bg-primary"
              :class="Number(hour.estimated_lost) > 0 ? '' : 'rounded-t-sm'"
              :style="{ height: barHeight(Number(hour.sold)) }"
              :title="`${hour.hour}h: ${formatQty(hour.sold)} vendidas`"
            />
          </div>
          <span class="op-micro tnum text-muted-foreground">{{ String(hour.hour).padStart(2, "0") }}h</span>
        </div>
      </div>
      <p v-else class="op-micro text-muted-foreground">Nenhuma venda registrada neste dia.</p>
      <p v-if="row.soldout_at" class="mt-0.5 op-micro" :class="row.verdict === 'short' ? 'text-destructive' : 'text-muted-foreground'">
        acabou {{ row.soldout_at }}<template v-if="hasEstimate"> · tracejado = estimativa</template>
      </p>
    </div>

    <div>
      <p class="mb-1.5 op-eyebrow text-muted-foreground">{{ row.soldout_at ? "Depois que acabou" : "O que ficou" }}</p>
      <ul v-if="row.unavailable.length || row.alert_requests" class="mb-1 flex flex-col gap-0.5 op-label leading-6" data-over-short-after>
        <li v-for="item in row.unavailable" :key="item.at" data-over-short-unavailable>
          {{ unavailableText(item) }}<span v-if="item.automatic" class="op-micro text-muted-foreground"> (automático)</span>
        </li>
        <li v-if="row.alert_requests" data-over-short-alerts>
          "Me avise" do site: <b>{{ clientCount(row.alert_requests) }}</b>
        </li>
      </ul>
      <template v-if="row.verdict === 'short'">
        <p class="op-label leading-6">
          Acabou às <b>{{ row.soldout_at }}</b> com {{ formatQty(row.sold) }} vendidas.
          <template v-if="row.lost_estimate">
            No ritmo até ali, o dia venderia ~{{ formatQty(String(demandEstimate)) }}: <b>~{{ formatQty(row.lost_estimate) }} vendas perdidas</b> <span class="op-micro text-muted-foreground">(estimativa)</span>.
          </template>
        </p>
      </template>
      <template v-else-if="row.verdict === 'over'">
        <p class="op-label leading-6">
          Sobraram <b>{{ formatQty(row.leftover) }} un.</b><template v-if="row.leftover_cost_q"> ({{ formatCostWhole(row.leftover_cost_q) }} de custo)</template>
          de {{ formatQty(row.made) }} feitas.
        </p>
      </template>
      <template v-else>
        <p class="op-label leading-6">
          Vendeu {{ formatQty(row.sold) }} de {{ formatQty(row.made) }}<template v-if="row.soldout_at">, e acabou perto de fechar</template>.
        </p>
      </template>
      <p v-if="row.typical_sold" class="op-label leading-6 text-muted-foreground">
        {{ capitalize(inTypical(day, compare)) }} vende ~{{ formatQty(row.typical_sold) }}; {{ historyText(row) }}.
      </p>
      <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        <a
          v-if="ordersHref"
          :href="ordersHref"
          :target="ordersLink.target"
          :rel="ordersLink.rel"
          class="inline-flex min-h-control items-center op-label font-semibold text-primary underline underline-offset-2"
          data-over-short-orders
        >{{ ordersLinkLabel(row.orders) }}</a>
        <button
          v-if="historyEntries.length"
          type="button"
          class="inline-flex min-h-control items-center op-label font-semibold text-primary underline underline-offset-2"
          :aria-expanded="showHistory"
          data-over-short-history
          @click="showHistory = !showHistory"
        >{{ historyDaysLabel(day, historyEntries.length) }}</button>
      </div>
      <ul v-if="showHistory" class="mt-1 flex flex-wrap gap-1.5" data-over-short-history-days>
        <li v-for="entry in historyEntries" :key="entry.iso">
          <NuxtLink
            :to="{ query: { ...route.query, day: entry.iso } }"
            class="inline-flex min-h-control items-center gap-1.5 rounded-full border border-border bg-card px-3 op-label hover:bg-accent"
          >
            <span class="tnum">{{ shortDate(entry.iso) }}</span>
            <span class="op-micro text-muted-foreground">{{ verdictMeta(entry.verdict).lower }}</span>
          </NuxtLink>
        </li>
      </ul>
    </div>
  </div>
</template>
