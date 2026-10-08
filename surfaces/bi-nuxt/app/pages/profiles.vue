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

// As quatro tabelas são NuxtTable. Coluna numérica alinha à direita, sem quebra; a
// porcentagem miúda vai na mesma célula, atrás do número.
const NUM = { th: "whitespace-nowrap text-right", td: "whitespace-nowrap text-right tnum text-foreground" } as const;
// O número e o espaço vão num texto só: dois textos vizinhos no `h()` viram um nó no
// HTML do servidor e dois no cliente, e a hidratação acusa diferença.
const withShare = (value: string, share: string) =>
  h("span", [`${value} `, h("span", { class: "op-micro text-muted-foreground" }, share)]);

const readingColumns = [
  { accessorKey: "label", header: "Perfil", meta: { class: { td: "font-medium" } } },
  { id: "orders", header: "Pedidos", meta: { class: NUM } },
  { id: "revenue", header: "Receita", meta: { class: NUM } },
  { id: "ticket", header: "Ticket", meta: { class: NUM } },
  {
    id: "items",
    header: () => h("span", { title: "unidades · produtos distintos por pedido" }, "Itens"),
    meta: { class: NUM },
  },
];
/** Linha "sem etiqueta" recua: é o resto, não um perfil. */
const readingMeta = {
  class: {
    tr: (row: { original: BIProfileRow }) => (row.original.profile === "unclassified" ? "text-muted-foreground" : ""),
  },
};

// Matriz faixa × perfil: as colunas de perfil vêm da leitura (A, B, C, sem etiqueta).
type MatrixRow = (typeof matrixRows.value)[number];
type MatrixCell = { row: { original: MatrixRow } };
const matrixColumns = computed(() => [
  {
    id: "band",
    header: "Faixa",
    meta: { class: { td: "font-medium text-foreground" } },
    cell: ({ row }: MatrixCell) => row.original.band.title,
  },
  { id: "total", header: "Pedidos", meta: { class: NUM }, cell: ({ row }: MatrixCell) => formatInt(row.original.total) },
  ...currentRows.value.map((profile, index) => ({
    id: `profile-${profile.profile}`,
    header: profile.profile === "unclassified" ? "Sem etiqueta" : profile.profile,
    meta: { class: NUM },
    cell: ({ row }: MatrixCell) => {
      const cell = row.original.cells[index];
      return cell ? withShare(formatInt(cell.orders), `(${formatPercent(cell.share)})`) : "";
    },
  })),
]);

// Bebida no pedido: dia da semana × faixa; o rodapé é a linha "Faixa" (o total por faixa).
type StrikeRow = (typeof strike.value)[number];
type StrikeCell = { row: { original: StrikeRow } };
const strikeColumns = computed(() => [
  {
    id: "weekday",
    // Cabeçalho vazio vira um texto vazio no cliente e nada no servidor (a hidratação
    // acusa diferença); o nome da coluna fica só para o leitor de tela.
    header: () => h("span", { class: "sr-only" }, "Dia da semana"),
    meta: { class: { td: "font-medium text-foreground" } },
    cell: ({ row }: StrikeCell) => row.original.label,
    footer: () => h("span", { class: "op-eyebrow text-muted-foreground" }, "Faixa"),
  },
  ...bandOptions.value.map((band, index) => ({
    id: `band-${band.key}`,
    header: band.label,
    meta: { class: NUM },
    cell: ({ row }: StrikeCell) => {
      const cell = row.original.cells[index];
      return h(
        "span",
        {
          class: cell && cell.orders ? "" : "text-muted-foreground",
          title: cell ? `${formatInt(cell.with_beverage)} de ${formatInt(cell.orders)}` : "",
        },
        cell && cell.orders ? formatPercent(cell.rate) : "sem pedido",
      );
    },
    footer: () =>
      h(
        "span",
        { class: "block text-right tnum" },
        strikeByBand.value[band.key]?.orders ? formatPercent(strikeByBand.value[band.key]!.rate) : "sem pedido",
      ),
  })),
  {
    id: "day",
    header: "Dia",
    meta: { class: NUM },
    cell: ({ row }: StrikeCell) => {
      const day = strikeByWeekday.value[row.original.weekday];
      return day?.orders ? formatPercent(day.rate) : "sem pedido";
    },
  },
]);

const revpashColumns = [
  { accessorKey: "title", header: "Faixa", meta: { class: { td: "font-medium text-foreground" } } },
  { id: "revenue", header: "Receita local", meta: { class: NUM } },
  {
    id: "denominator",
    header: "Denominador",
    meta: { class: { th: "text-right", td: "text-right op-micro tnum text-muted-foreground" } },
  },
  { id: "revpash", header: "Receita por assento-hora", meta: { class: NUM } },
];
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Quem compra no balcão?">
      <template #status>
        <BiLiveStatus :pending="pending" :error="error" />
      </template>
      <template #actions>
        <BiWindowPicker class="max-md:hidden" />
        <BiPageMenu />
      </template>
      <template #phone-actions>
        <BiPeriodChip />
        <BiShareButton />
      </template>
      <template #filters>
        <label class="inline-flex items-center gap-2 op-label text-muted-foreground">
          Dia da semana
          <UiNativeSelect
            :value="filters.weekday"
            @change="apply({ weekday: ($event.target as HTMLSelectElement).value })"
          >
            <option value="">Todos</option>
            <option v-for="(label, index) in WEEKDAY_LABELS" :key="label" :value="String(index)">{{ label }}</option>
          </UiNativeSelect>
        </label>
        <label class="inline-flex items-center gap-2 op-label text-muted-foreground">
          Faixa de hora
          <UiNativeSelect
            :value="filters.hour_band"
            @change="apply({ hour_band: ($event.target as HTMLSelectElement).value })"
          >
            <option value="">Todas</option>
            <option v-for="band in bandOptions" :key="band.key" :value="band.key">{{ band.title }}</option>
          </UiNativeSelect>
        </label>
      </template>
    </OperatorPageHeader>

    <main class="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
      <p class="op-micro text-muted-foreground">
        Perfil <strong>presumido</strong> pela cesta: cada produto tem uma vocação (consome aqui · leva ·
        híbrido) editável em Configurações › Como vendemos. Entrega e iFood ficam fora da pergunta e dentro
        da conta. A hora é a do registro da venda.
      </p>

      <BiPageState :pending="pending && !report" :error="error" @retry="refresh()" />
      <template v-if="report">
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

      <!-- As três leituras lado a lado: um cartão por leitura, cada um com a tabela
           integrada (a tabela é o corpo inteiro do cartão). -->
      <section class="flex flex-col gap-3" aria-labelledby="bi-readings-heading" data-bi-readings>
        <div>
          <h2 id="bi-readings-heading" class="op-title text-foreground">Os três perfis, em três leituras</h2>
          <p class="op-micro text-muted-foreground">
            Piso lê o ambíguo como levar; teto, como consumo local; vigente é a regra do explorador. % sobre os
            pedidos e a receita de balcão do recorte.
          </p>
        </div>
        <div class="grid gap-3 xl:grid-cols-3">
          <NuxtCard v-for="reading in report.readings" :key="reading.key" class="min-w-0" :data-bi-reading="reading.key">
            <template #header>
              <h3 class="op-label font-semibold text-foreground">{{ reading.label }}</h3>
            </template>
            <NuxtTable
              :data="readingRows(reading.key)"
              :columns="readingColumns"
              :meta="readingMeta"
              :get-row-id="(row) => row.profile"
              :caption="`Perfis na leitura ${reading.label}`"
            >
              <template #orders-cell="{ row }">
                {{ formatInt(row.original.orders) }}
                <span class="op-micro text-muted-foreground">{{ formatPercent(row.original.orders_share) }}</span>
              </template>
              <template #revenue-cell="{ row }">
                {{ formatMoneyCompact(row.original.revenue_q) }}
                <span class="op-micro text-muted-foreground">{{ formatPercent(row.original.revenue_share) }}</span>
              </template>
              <template #ticket-cell="{ row }">{{ formatMoney(row.original.average_ticket_q) }}</template>
              <template #items-cell="{ row }">{{ formatQty(row.original.units_per_order) }} · {{ formatQty(row.original.distinct_per_order) }}</template>
            </NuxtTable>
          </NuxtCard>
        </div>
      </section>

      <BiSection
        title="Estimativa ponderada: quantos comeram aqui"
        caption="A vocação em graus: cada produto tem um peso (% de chance de ser consumido aqui, editável em Configurações › Como vendemos, por papel e por produto) e a cesta vale o seu maior peso. É esperança sob os pesos vigentes, não medida; a faixa entre piso e teto abaixo continua sendo o que o dado garante."
      >
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
          <NuxtCard data-bi-seated-by-band>
            <p class="op-eyebrow text-muted-foreground">Por faixa · % que comeu aqui</p>
            <ul class="mt-1 flex flex-col gap-0.5 op-label">
              <li v-for="(band, index) in bandOptions" :key="band.key" class="flex justify-between tnum">
                <span class="text-muted-foreground">{{ band.label }}</span>
                <span class="text-foreground">{{ report.estimate.orders_by_band[index] ? formatPercent(Math.round((report.estimate.seated_by_band[index]! * 1000) / report.estimate.orders_by_band[index]!) / 10) : 'sem pedido' }}</span>
              </li>
            </ul>
          </NuxtCard>
        </div>
      </BiSection>

      <div class="grid items-start gap-3 lg:grid-cols-2">
        <BiSection
          title="A faixa honesta"
          :caption="sensitivityHeadline(report.sensitivity.orders_changed, report.sensitivity.share_changed, report.counter_orders)"
        >
          <ul class="flex flex-col gap-2 op-label">
            <li v-for="range in report.sensitivity.ranges" :key="range.profile" class="flex flex-col">
              <span class="font-medium text-foreground">{{ range.label }}</span>
              <span class="tnum text-foreground">{{ rangeText(range) }}</span>
              <span v-if="previousByProfile[range.profile]" class="op-micro tnum text-muted-foreground">
                vigente {{ formatPercent(currentRows.find((r) => r.profile === range.profile)?.orders_share ?? 0) }}
                · período anterior {{ formatPercent(previousByProfile[range.profile]!.orders_share) }}
                ({{ formatInt(previousByProfile[range.profile]!.orders) }} pedidos)
              </span>
            </li>
          </ul>
        </BiSection>

        <BiSection
          title="Conciliação"
          caption="A + B + C + sem etiqueta + entrega = faturamento do recorte. Sem filtros, é o mesmo número da aba Vendas."
        >
          <dl class="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 op-label">
            <dt class="text-muted-foreground">Balcão · {{ formatInt(report.counter_orders) }} pedidos</dt>
            <dd class="text-right tnum text-foreground">{{ formatMoney(report.counter_revenue_q) }}</dd>
            <dt class="text-muted-foreground">Entrega e iFood · {{ formatInt(report.delivery_orders) }} pedidos (fora da pergunta)</dt>
            <dd class="text-right tnum text-foreground">{{ formatMoney(report.delivery_revenue_q) }}</dd>
            <dt class="border-t border-border pt-1 font-medium text-foreground">Faturamento do recorte</dt>
            <dd class="border-t border-border pt-1 text-right font-medium tnum text-foreground">{{ formatMoney(report.revenue_total_q) }}</dd>
          </dl>
        </BiSection>
      </div>

      <BiSection title="Perfil por faixa de hora" data-bi-profile-matrix>
        <template #caption>
          Pedidos por faixa e % dentro da faixa. Quem almoça às 13h e paga às 14h05 cai em "Tarde".
        </template>
        <template #aside>
          <label class="inline-flex items-center gap-2 op-label text-muted-foreground">
            Leitura
            <UiNativeSelect v-model="matrixReading">
              <option v-for="reading in report.readings" :key="reading.key" :value="reading.key">{{ reading.label }}</option>
            </UiNativeSelect>
          </label>
        </template>
        <NuxtTable
          :data="matrixRows"
          :columns="matrixColumns"
          :get-row-id="(row) => row.band.key"
          caption="Pedidos por faixa de hora e perfil"
        />
      </BiSection>

      <div class="grid items-start gap-3 lg:grid-cols-2">
        <BiSection title="Receita por categoria">
          <template #caption>
            Soma das linhas de balcão (histórico: categoria do Yooga; nativo: coleção do catálogo).
            Difere do faturamento por {{ formatMoney(report.category_header_gap_q) }} de desconto/acréscimo de venda.
          </template>
          <div class="mb-3 rounded-md bg-muted p-2 op-label">
            <span class="font-medium text-foreground">Bebida pronta industrializada:</span>
            <span class="tnum text-foreground"> {{ formatMoney(report.beverage.ready_revenue_q) }}</span>
            <span class="text-muted-foreground"> · {{ formatPercent(report.beverage.ready_share) }} do faturamento de balcão</span>
          </div>
          <ChartHBarList v-if="categoryRows.length" :rows="categoryRows" />
          <p v-else class="op-label text-muted-foreground">Sem vendas no recorte.</p>
        </BiSection>

        <BiSection
          title="Bebida no pedido"
          caption="A bebida indica o perfil, mas não decide: há C sem bebida (doce na mesa) e o café pra levar aumenta B e C."
        >
          <div class="mb-3 grid grid-cols-2 gap-2 xl:grid-cols-4">
            <StatTile label="Com bebida" :value="formatPercent(report.beverage.strike_rate)" :hint="`${formatInt(report.beverage.orders_with_beverage)} pedidos`" />
            <StatTile label="Com café/chá preparado" :value="formatPercent(report.beverage.prepared_rate)" />
            <StatTile label="Bebidas por pedido local" :value="formatQty(report.beverage.per_local_order)" :hint="`${formatInt(report.beverage.local_orders)} pedidos com item local`" />
            <StatTile
              label="Só bebida, nada mais"
              :value="formatPercent(report.beverage.beverage_only_share)"
              :hint="`${formatInt(report.beverage.beverage_only_orders)} pedidos · ticket ${formatMoney(report.beverage.beverage_only_ticket_q)} · medido, não estimado`"
            />
          </div>
          <p class="mb-1 op-eyebrow text-muted-foreground">% de pedidos com bebida · dia da semana × faixa (período inteiro)</p>
          <NuxtTable
            :data="strike"
            :columns="strikeColumns"
            :get-row-id="(row) => String(row.weekday)"
            caption="Pedidos com bebida por dia da semana e faixa"
            data-bi-beverage-strike
          />
        </BiSection>
      </div>

      <BiSection title="Receita por assento por hora" data-bi-revpash>
        <template #caption>
          Receita dos pedidos com item local ÷ (assentos × horas da faixa × dias com venda). Assentos:
          {{ formatInt(report.seats) }} ({{ report.seats_source }}). Todas as faixas do recorte de dia da semana.
        </template>
        <NuxtTable :data="report.revpash" :columns="revpashColumns" :get-row-id="(row) => row.band" caption="Receita por assento-hora por faixa">
          <template #revenue-cell="{ row }">{{ formatMoney(row.original.revenue_local_q) }}</template>
          <template #denominator-cell="{ row }">{{ revpashHint(row.original.seats, row.original.hours, row.original.days) }}</template>
          <template #revpash-cell="{ row }">{{ formatMoney(row.original.revpash_q) }}</template>
        </NuxtTable>
      </BiSection>
      </template>
      <BiSwipeHint />
    </main>
  </div>
</template>
