<script setup lang="ts">
// "Ver lotes e vendas" (prévia `bi-sobra4.html`, pino 7): aprofundar sem trocar de tela.
// Os lotes do dia (o registro de onde o "fez" saiu, cada um leva ao Fechamento da
// Produção daquele dia, e o lote que o plano tinha e não fechou), as vendas por hora
// (cheio = vendido; tracejado = a estimativa depois que acabou) e o que aconteceu
// depois: quando os canais tiraram o produto do ar, quantos pediram "Me avise", e os
// caminhos ao registro (os pedidos do dia no Gestor, os dias da comparação). Links e
// ações são NuxtButton (`to` para ir; `ghost` primário para o caminho em texto).
import type { BIOverShortRow } from "~/types/bi";
import type {
  ReadingChartPoint,
  ReadingChartSeries,
} from "../../../operator-kit/app/presentation/readingChart";
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

const hasEstimate = computed(() => props.row.sales_by_hour.some((hour) => Number(hour.estimated_lost) > 0));
const hourSeries = computed<ReadingChartSeries[]>(() => [
  { key: "sold", label: "Vendidas" },
  ...(hasEstimate.value ? [{ key: "lost", label: "Perdidas (estimativa)", tone: "error" as const }] : []),
]);
const hourPoints = computed<ReadingChartPoint[]>(() =>
  props.row.sales_by_hour.map((hour) => ({
    label: `${String(hour.hour).padStart(2, "0")}h`,
    values: { sold: Number(hour.sold), lost: Number(hour.estimated_lost) },
  })),
);

const capitalize = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
const demandEstimate = computed(() => Number(props.row.sold) + Number(props.row.lost_estimate || 0));
const missingLot = computed(() => props.row.planned_lots > props.row.lots.length);
const historyEntries = computed(() =>
  props.row.history_days.map((iso, index) => ({ iso, verdict: props.row.history[index] ?? "right" })),
);
</script>

<template>
  <!-- Lotes, vendas por hora e o que aconteceu depois, em três colunas iguais do
       desktop largo para cima; abaixo, empilhados. -->
  <div class="grid gap-5 whitespace-normal rounded-md bg-primary/5 px-4 py-3 lg:grid-cols-3" data-over-short-detail>
    <div>
      <h3 class="mb-1.5 text-sm font-medium text-highlighted">Lotes do dia</h3>
      <NuxtButton
        v-for="lot in row.lots"
        :key="lot.ref"
        :to="closeUrl || undefined"
        :target="closeLink.target"
        :rel="closeLink.rel"
        color="neutral"
        variant="ghost"
        trailing-icon="i-lucide-arrow-up-right"
        block
        class="justify-start"
        :aria-label="`Lote ${lot.ref}, ${formatQty(lot.qty)} unidades: abrir o Fechamento da Produção`"
        data-over-short-lot
      >
        <span class="font-mono text-primary">{{ lot.ref }}</span>
        <span v-if="lot.finished_at" class="tnum text-muted-foreground">saiu {{ lot.finished_at }}</span>
        <span class="ml-auto tnum font-semibold">{{ formatQty(lot.qty) }} un.</span>
      </NuxtButton>
      <p class="mt-1 op-micro" :class="missingLot ? 'font-medium text-foreground' : 'text-muted-foreground'" data-over-short-lots-line>
        {{ lotsLine(row) }}
      </p>
    </div>

    <div class="min-w-0">
      <h3 class="mb-1.5 text-sm font-medium text-highlighted">Vendas por hora</h3>
      <!-- O gráfico de leitura do kit (laudo F03): cheio = vendido; a segunda série,
           a estimativa do que se perdeu depois que acabou. Toque, mouse e setas leem
           cada hora; a tabela equivalente sai no SSR. -->
      <OperatorReadingChart
        :title="`Vendas por hora de ${row.name}`"
        axis-label="Hora"
        :series="hourSeries"
        :points="hourPoints"
        :format="(value) => formatQty(String(value))"
        :height="140"
        :max-ticks="8"
        empty-title="Nenhuma venda registrada neste dia"
      />
      <p v-if="row.soldout_at" class="mt-0.5 text-xs" :class="row.verdict === 'short' ? 'text-error' : 'text-muted'">
        acabou {{ row.soldout_at }}
      </p>
    </div>

    <div>
      <h3 class="mb-1.5 text-sm font-medium text-highlighted">{{ row.soldout_at ? "Depois que acabou" : "O que ficou" }}</h3>
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
        <NuxtButton
          v-if="ordersHref"
          :to="ordersHref"
          :target="ordersLink.target"
          :rel="ordersLink.rel"
          color="primary"
          variant="ghost"
          :label="ordersLinkLabel(row.orders)"
          data-over-short-orders
        />
        <NuxtButton
          v-if="historyEntries.length"
          color="primary"
          variant="ghost"
          :label="historyDaysLabel(day, historyEntries.length)"
          :aria-expanded="showHistory"
          data-over-short-history
          @click="showHistory = !showHistory"
        />
      </div>
      <ul v-if="showHistory" class="mt-1 flex flex-wrap gap-1.5" data-over-short-history-days>
        <li v-for="entry in historyEntries" :key="entry.iso">
          <NuxtButton
            :to="{ query: { ...route.query, day: entry.iso } }"
            color="neutral"
            variant="outline"
          >
            <span class="tnum">{{ shortDate(entry.iso) }}</span>
            <span class="op-micro text-muted-foreground">{{ verdictMeta(entry.verdict).lower }}</span>
          </NuxtButton>
        </li>
      </ul>
    </div>
  </div>
</template>
