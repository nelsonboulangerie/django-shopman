<script setup lang="ts">
// Perfis de consumo do balcão (BI-CONSUMPTION-PROFILES) — quem são os clientes,
// em três perfis PRESUMIDOS pela cesta: A só pra levar · B local + levar ·
// C só local. Entrega/iFood ficam fora da pergunta e dentro da conciliação.
//
// O híbrido (croissant, doce) não decide sozinho, então a tela mostra as três
// leituras lado a lado — piso, vigente, teto — e quanto muda entre elas. O
// número honesto é a faixa; a leitura vigente é a que o explorador usa.
import type { BIProfileRow } from "~/generated/biContract";
import {
  WEEKDAY_LABELS,
  delta,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  formatQty,
  rangeText,
  revpashHint,
  sensitivityHeadline,
  strikeMatrix,
} from "~/presentation/bi";

const { filters, report, pending, error, refresh, apply } = useBiProfiles();

// A matriz perfil × faixa e as barras leem UMA leitura por vez; começa na vigente.
const matrixReading = ref("current");

const readingRows = (reading: string): BIProfileRow[] =>
  (report.value?.profiles ?? []).filter((row) => row.reading === reading);

const currentRows = computed(() => readingRows("current"));
const previousByProfile = computed(() =>
  Object.fromEntries((report.value?.previous.rows ?? []).map((row) => [row.profile, row])),
);

// Faixas do expediente (a última do contrato é "fora do expediente": entra na
// matriz como coluna declarada, mas não vira opção de filtro).
const bands = computed(() => report.value?.bands ?? []);
const bandOptions = computed(() => bands.value.filter((b) => b.key !== "outside"));

const matrixRows = computed(() => {
  const rows = readingRows(matrixReading.value);
  return bands.value.map((band, index) => {
    const total = rows.reduce((sum, row) => sum + (row.orders_by_band[index] ?? 0), 0);
    return {
      band,
      total,
      cells: rows.map((row) => ({
        profile: row.profile,
        orders: row.orders_by_band[index] ?? 0,
        share: total ? Math.round(((row.orders_by_band[index] ?? 0) * 1000) / total) / 10 : 0,
        revenue_q: row.revenue_by_band_q[index] ?? 0,
      })),
    };
  });
});

const categoryRows = computed(() =>
  (report.value?.categories ?? []).slice(0, 12).map((row) => ({
    label: row.category,
    value: row.revenue_q,
    display: `${formatMoneyCompact(row.revenue_q)} · ${formatPercent(row.share)}`,
    hint: row.ready_beverage_q
      ? `bebida pronta industrializada: ${formatMoney(row.ready_beverage_q)}`
      : undefined,
  })),
);

const strike = computed(() =>
  strikeMatrix(report.value?.beverage.by_weekday_band ?? [], bandOptions.value.map((b) => b.key)),
);
const strikeByBand = computed(() =>
  Object.fromEntries((report.value?.beverage.by_band ?? []).map((c) => [c.band, c])),
);
const strikeByWeekday = computed(() =>
  Object.fromEntries((report.value?.beverage.by_weekday ?? []).map((c) => [c.weekday, c])),
);

const selectClass =
  "h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground";
const thClass = "whitespace-nowrap pb-2 pl-2 text-right text-xs font-medium text-muted-foreground";
const tdClass = "whitespace-nowrap py-1.5 pl-2 text-right tabular-nums text-foreground";
</script>

<template>
  <main class="flex flex-1 flex-col gap-4 p-4">
    <section class="flex flex-wrap items-end gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="text-lg font-semibold text-foreground">Perfis de consumo do balcão</h1>
        <p class="text-xs text-muted-foreground">
          Perfil <strong>presumido</strong> pela cesta: cada produto tem uma vocação (consome aqui · leva ·
          híbrido) editável em Configurações › Como vendemos. Entrega e iFood ficam fora da pergunta e dentro
          da conta. A hora é a do registro da venda.
        </p>
      </div>
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Dia da semana
        <select
          :value="filters.weekday"
          :class="selectClass"
          @change="apply({ weekday: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">Todos</option>
          <option v-for="(label, index) in WEEKDAY_LABELS" :key="label" :value="String(index)">{{ label }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
        Faixa de hora
        <select
          :value="filters.hour_band"
          :class="selectClass"
          @change="apply({ hour_band: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">Todas</option>
          <option v-for="band in bandOptions" :key="band.key" :value="band.key">{{ band.title }}</option>
        </select>
      </label>
    </section>

    <p v-if="pending" class="text-sm text-muted-foreground">Carregando…</p>
    <div v-else-if="error" class="flex items-center gap-3">
      <p class="text-sm text-muted-foreground">Não deu para carregar os números.</p>
      <button type="button" class="h-9 rounded-md border border-border px-3 text-sm font-medium" @click="refresh()">
        Tentar de novo
      </button>
    </div>
    <template v-else-if="report">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Pedidos de balcão"
          :value="formatInt(report.counter_orders)"
          :delta="delta(report.counter_orders, report.previous.counter_orders)"
        />
        <StatTile
          label="Faturamento de balcão"
          :value="formatMoneyCompact(report.counter_revenue_q)"
          :delta="delta(report.counter_revenue_q, report.previous.counter_revenue_q)"
        />
        <StatTile
          label="Cobertura das etiquetas"
          :value="formatPercent(report.coverage)"
          hint="Pedidos com ao menos um produto etiquetado; o resto sai 'sem etiqueta'"
        />
        <StatTile
          label="Mudam de perfil piso→teto"
          :value="formatPercent(report.sensitivity.share_changed)"
          :hint="`${formatInt(report.sensitivity.orders_changed)} pedidos com só ambíguos no que decide`"
        />
      </div>

      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">Os três perfis, em três leituras</h2>
        <p class="mb-3 text-xs text-muted-foreground">
          Piso lê o ambíguo como levar; teto, como consumo local; vigente é a regra do explorador. % sobre os
          pedidos e a receita de balcão do recorte.
        </p>
        <div class="grid gap-4 xl:grid-cols-3">
          <div v-for="reading in report.readings" :key="reading.key" class="min-w-0 overflow-x-auto">
            <h3 class="mb-1 text-sm font-semibold text-foreground">{{ reading.label }}</h3>
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border">
                  <th class="pb-2 text-left text-xs font-medium text-muted-foreground">Perfil</th>
                  <th :class="thClass">Pedidos</th>
                  <th :class="thClass">Receita</th>
                  <th :class="thClass">Ticket</th>
                  <th :class="thClass" title="unidades · produtos distintos por pedido">Itens</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in readingRows(reading.key)"
                  :key="row.profile"
                  class="border-b border-border last:border-0"
                  :class="row.profile === 'unclassified' ? 'text-muted-foreground' : ''"
                >
                  <td class="py-1.5 pr-2 font-medium">{{ row.label }}</td>
                  <td :class="tdClass">
                    {{ formatInt(row.orders) }}
                    <span class="text-xs text-muted-foreground">{{ formatPercent(row.orders_share) }}</span>
                  </td>
                  <td :class="tdClass">
                    {{ formatMoneyCompact(row.revenue_q) }}
                    <span class="text-xs text-muted-foreground">{{ formatPercent(row.revenue_share) }}</span>
                  </td>
                  <td :class="tdClass">{{ formatMoney(row.average_ticket_q) }}</td>
                  <td :class="tdClass">{{ formatQty(row.units_per_order) }} · {{ formatQty(row.distinct_per_order) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">Estimativa ponderada: quantos comeram aqui</h2>
        <p class="mb-3 text-xs text-muted-foreground">
          A vocação em graus: cada produto tem um peso (% de chance de ser consumido aqui, editável em
          Configurações › Como vendemos, por papel e por produto) e a cesta vale o seu maior peso. É esperança
          sob os pesos vigentes, não medida; a faixa piso–teto abaixo continua sendo o que o dado garante.
        </p>
        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile
            label="Alguém comeu aqui"
            :value="`≈ ${formatInt(Math.round(report.estimate.seated_orders))}`"
            :hint="`${formatPercent(report.estimate.seated_share)} dos pedidos com peso · ${formatMoneyCompact(report.estimate.seated_revenue_q)} (${formatPercent(report.estimate.seated_revenue_share)} da receita)`"
            :delta="delta(report.estimate.seated_share, report.previous.estimate.seated_share)"
          />
          <StatTile
            label="Só vieram buscar"
            :value="`≈ ${formatInt(Math.round(report.estimate.takeaway_orders))}`"
            :hint="`${formatPercent(report.estimate.takeaway_share)} dos pedidos com peso`"
          />
          <StatTile
            label="Pedidos com peso"
            :value="formatInt(report.estimate.weighted_orders)"
            :hint="report.estimate.unweighted_orders ? `${formatInt(report.estimate.unweighted_orders)} sem peso ficam fora desta conta` : 'todos os pedidos de balcão entraram'"
          />
          <div class="rounded-md border border-border bg-card p-3">
            <p class="text-xs font-medium text-muted-foreground">Por faixa · % que comeu aqui</p>
            <ul class="mt-1 flex flex-col gap-0.5 text-sm">
              <li v-for="(band, index) in bandOptions" :key="band.key" class="flex justify-between tabular-nums">
                <span class="text-muted-foreground">{{ band.label }}</span>
                <span class="text-foreground">{{ report.estimate.orders_by_band[index] ? formatPercent(Math.round((report.estimate.seated_by_band[index]! * 1000) / report.estimate.orders_by_band[index]!) / 10) : '—' }}</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">A faixa honesta</h2>
          <p class="mb-3 text-xs text-muted-foreground">
            {{ sensitivityHeadline(report.sensitivity.orders_changed, report.sensitivity.share_changed, report.counter_orders) }}
          </p>
          <ul class="flex flex-col gap-2 text-sm">
            <li v-for="range in report.sensitivity.ranges" :key="range.profile" class="flex flex-col">
              <span class="font-medium text-foreground">{{ range.label }}</span>
              <span class="tabular-nums text-foreground">{{ rangeText(range) }}</span>
              <span v-if="previousByProfile[range.profile]" class="text-xs tabular-nums text-muted-foreground">
                vigente {{ formatPercent(currentRows.find((r) => r.profile === range.profile)?.orders_share ?? 0) }}
                · período anterior {{ formatPercent(previousByProfile[range.profile]!.orders_share) }}
                ({{ formatInt(previousByProfile[range.profile]!.orders) }} pedidos)
              </span>
            </li>
          </ul>
        </section>

        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Conciliação</h2>
          <p class="mb-3 text-xs text-muted-foreground">
            A + B + C + sem etiqueta + entrega = faturamento do recorte. Sem filtros, é o mesmo número da aba Vendas.
          </p>
          <dl class="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
            <dt class="text-muted-foreground">Balcão · {{ formatInt(report.counter_orders) }} pedidos</dt>
            <dd class="text-right tabular-nums text-foreground">{{ formatMoney(report.counter_revenue_q) }}</dd>
            <dt class="text-muted-foreground">Entrega e iFood · {{ formatInt(report.delivery_orders) }} pedidos (fora da pergunta)</dt>
            <dd class="text-right tabular-nums text-foreground">{{ formatMoney(report.delivery_revenue_q) }}</dd>
            <dt class="border-t border-border pt-1 font-medium text-foreground">Faturamento do recorte</dt>
            <dd class="border-t border-border pt-1 text-right font-medium tabular-nums text-foreground">{{ formatMoney(report.revenue_total_q) }}</dd>
          </dl>
        </section>
      </div>

      <section class="rounded-md border border-border bg-card p-3">
        <div class="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-foreground">Perfil por faixa de hora</h2>
            <p class="text-xs text-muted-foreground">
              Pedidos por faixa e % dentro da faixa. Quem almoça às 13h e paga às 14h05 cai em "Tarde".
            </p>
          </div>
          <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
            Leitura
            <select v-model="matrixReading" :class="selectClass">
              <option v-for="reading in report.readings" :key="reading.key" :value="reading.key">{{ reading.label }}</option>
            </select>
          </label>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-border">
                <th class="pb-2 text-left text-xs font-medium text-muted-foreground">Faixa</th>
                <th :class="thClass">Pedidos</th>
                <th v-for="row in currentRows" :key="row.profile" :class="thClass">{{ row.profile === 'unclassified' ? 'Sem etiqueta' : row.profile }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in matrixRows" :key="row.band.key" class="border-b border-border last:border-0">
                <td class="py-1.5 pr-2 font-medium text-foreground">{{ row.band.title }}</td>
                <td :class="tdClass">{{ formatInt(row.total) }}</td>
                <td v-for="cell in row.cells" :key="cell.profile" :class="tdClass">
                  {{ formatInt(cell.orders) }}
                  <span class="text-xs text-muted-foreground">({{ formatPercent(cell.share) }})</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Receita por categoria</h2>
          <p class="mb-3 text-xs text-muted-foreground">
            Soma das linhas de balcão (histórico: categoria do Yooga; nativo: coleção do catálogo).
            Difere do faturamento por {{ formatMoney(report.category_header_gap_q) }} de desconto/acréscimo de venda.
          </p>
          <div class="mb-3 rounded-md bg-muted p-2 text-sm">
            <span class="font-medium text-foreground">Bebida pronta industrializada:</span>
            <span class="tabular-nums text-foreground"> {{ formatMoney(report.beverage.ready_revenue_q) }}</span>
            <span class="text-muted-foreground"> · {{ formatPercent(report.beverage.ready_share) }} do faturamento de balcão</span>
          </div>
          <ChartHBarList v-if="categoryRows.length" :rows="categoryRows" />
          <p v-else class="text-sm text-muted-foreground">Sem vendas no recorte.</p>
        </section>

        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Bebida no pedido</h2>
          <p class="mb-3 text-xs text-muted-foreground">
            Bebida é proxy parcial: existe C sem bebida (doce na mesa) e café pra levar infla B/C.
          </p>
          <div class="mb-3 grid grid-cols-3 gap-2">
            <StatTile label="Com bebida" :value="formatPercent(report.beverage.strike_rate)" :hint="`${formatInt(report.beverage.orders_with_beverage)} pedidos`" />
            <StatTile label="Com café/chá preparado" :value="formatPercent(report.beverage.prepared_rate)" />
            <StatTile label="Bebidas por pedido local" :value="formatQty(report.beverage.per_local_order)" :hint="`${formatInt(report.beverage.local_orders)} pedidos com item local`" />
          </div>
          <p class="mb-1 text-xs font-medium text-muted-foreground">% de pedidos com bebida · dia da semana × faixa (período inteiro)</p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border">
                  <th class="pb-2 text-left text-xs font-medium text-muted-foreground"></th>
                  <th v-for="band in bandOptions" :key="band.key" :class="thClass">{{ band.label }}</th>
                  <th :class="thClass">Dia</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in strike" :key="row.weekday" class="border-b border-border last:border-0">
                  <td class="py-1 pr-2 font-medium text-foreground">{{ row.label }}</td>
                  <td v-for="(cell, index) in row.cells" :key="index" :class="tdClass" :title="cell ? `${formatInt(cell.with_beverage)} de ${formatInt(cell.orders)}` : ''">
                    <span :class="cell && cell.orders ? '' : 'text-muted-foreground'">{{ cell && cell.orders ? formatPercent(cell.rate) : '—' }}</span>
                  </td>
                  <td :class="tdClass">{{ strikeByWeekday[row.weekday]?.orders ? formatPercent(strikeByWeekday[row.weekday]!.rate) : '—' }}</td>
                </tr>
                <tr>
                  <td class="py-1 pr-2 text-xs font-medium text-muted-foreground">Faixa</td>
                  <td v-for="band in bandOptions" :key="band.key" :class="tdClass">{{ strikeByBand[band.key]?.orders ? formatPercent(strikeByBand[band.key]!.rate) : '—' }}</td>
                  <td :class="tdClass"></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">RevPASH por faixa</h2>
        <p class="mb-3 text-xs text-muted-foreground">
          Receita dos pedidos com item local ÷ (assentos × horas da faixa × dias com venda). Assentos:
          {{ formatInt(report.seats) }} — {{ report.seats_source }}. Todas as faixas do recorte de dia da semana.
        </p>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-border">
                <th class="pb-2 text-left text-xs font-medium text-muted-foreground">Faixa</th>
                <th :class="thClass">Receita local</th>
                <th :class="thClass">Denominador</th>
                <th :class="thClass">RevPASH</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.revpash" :key="row.band" class="border-b border-border last:border-0">
                <td class="py-1.5 pr-2 font-medium text-foreground">{{ row.title }}</td>
                <td :class="tdClass">{{ formatMoney(row.revenue_local_q) }}</td>
                <td class="py-1.5 text-right text-xs tabular-nums text-muted-foreground">{{ revpashHint(row.seats, row.hours, row.days) }}</td>
                <td :class="tdClass">{{ formatMoney(row.revpash_q) }} <span class="text-xs text-muted-foreground">/ assento-hora</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>
