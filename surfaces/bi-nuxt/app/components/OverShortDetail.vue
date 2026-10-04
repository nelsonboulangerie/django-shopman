<script setup lang="ts">
// "Ver lotes e vendas" (prévia `bi-sobra4.html`, pino 7): aprofundar sem trocar de tela.
// Os lotes do dia (o registro de onde o "fez" saiu, cada um leva ao Fechamento da
// Produção daquele dia), as vendas por hora (cheio = vendido; tracejado = a estimativa
// depois que acabou) e o que a leitura conclui, com o caminho para o plano.
import type { BIOverShortRow } from "~/types/bi";
import { formatQty } from "~/presentation/bi";
import { formatCostWhole, historyText, inTypical } from "~/presentation/overShort";

const props = defineProps<{
  row: BIOverShortRow;
  day: string;
  /** Link do Fechamento da Produção daquele dia (os lotes moram lá). */
  closeUrl: string;
  planUrl: string;
  planLabel: string;
}>();

const { attrsFor } = useOperatorAppLink();
const closeLink = computed(() => attrsFor(props.closeUrl));
const planLink = computed(() => attrsFor(props.planUrl));

const hourMax = computed(() =>
  Math.max(1, ...props.row.sales_by_hour.map((hour) => Number(hour.sold) + Number(hour.estimated_lost))),
);
const barHeight = (value: number) => `${Math.max(value > 0 ? 6 : 0, (value / hourMax.value) * 64)}px`;

const capitalize = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
const lotsTotal = computed(() => props.row.lots.reduce((sum, lot) => sum + Number(lot.qty), 0));
const hasEstimate = computed(() => props.row.sales_by_hour.some((hour) => Number(hour.estimated_lost) > 0));
const demandEstimate = computed(() => Number(props.row.sold) + Number(props.row.lost_estimate || 0));
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
      <p class="mt-1 op-micro text-muted-foreground">
        {{ row.lots.length === 1 ? "1 lote" : `${row.lots.length} lotes` }} · {{ formatQty(String(lotsTotal)) }} un. feitas
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
        {{ capitalize(inTypical(day)) }} vende ~{{ formatQty(row.typical_sold) }}; {{ historyText(row) }}.
      </p>
      <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        <a
          v-if="planUrl"
          :href="planUrl"
          :target="planLink.target"
          :rel="planLink.rel"
          class="inline-flex min-h-control items-center op-label font-semibold text-primary underline underline-offset-2"
        >{{ planLabel }}</a>
        <a
          :href="closeUrl"
          :target="closeLink.target"
          :rel="closeLink.rel"
          class="inline-flex min-h-control items-center op-label font-semibold text-primary underline underline-offset-2"
        >Os lotes no Fechamento</a>
      </div>
    </div>
  </div>
</template>
