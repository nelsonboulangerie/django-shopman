<script setup lang="ts">
// Caixa — quebra por dia e por operador, sangrias/suprimentos e o mix de
// pagamento consolidado pelo fechamento. `closings_missing` fica à vista:
// buraco declarado, nunca silenciado.
//
// Esta tela é a AUDITORIA DO DONO: o endpoint exige `cashman.audit_shift`, que só o
// grupo Dono concede. A decisão do fechamento às cegas (SUITE-UX §15: "o número só
// existe na auditoria do Dono") é o que permite o valor aqui e em nenhum outro lugar;
// o cabeçalho diz isso em vez de deixar o leitor adivinhar por que vê R$.
import type { BICashReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  bucketLabel,
  bucketRows,
  cashAnswer,
  delta,
  formatInt,
  formatMoney,
} from "~/presentation/bi";

const { report, pending, error, refresh } = useBiReport<BICashReport>("cash");

const differenceSeries = computed(() =>
  bucketRows(report.value?.days ?? []).map((bucket) => {
    const shifts = bucket.rows.reduce((sum, d) => sum + d.shifts, 0);
    const sangria = bucket.rows.reduce((sum, d) => sum + d.sangria_q, 0);
    const suprimento = bucket.rows.reduce((sum, d) => sum + d.suprimento_q, 0);
    return {
      label: bucketLabel(bucket.date, bucket.span),
      value: bucket.rows.reduce((sum, d) => sum + d.difference_q, 0),
      detail: [
        BUCKET_SPAN_LABELS[bucket.span],
        `${formatInt(shifts)} turno${shifts === 1 ? "" : "s"}`,
        `sangria ${formatMoney(sangria)}`,
        `suprimento ${formatMoney(suprimento)}`,
      ]
        .filter(Boolean)
        .join(" · "),
    };
  }),
);

const methodRows = computed(() =>
  (report.value?.payment_methods ?? []).map((row) => ({
    label: row.method,
    value: row.amount_q,
    display: formatMoney(row.amount_q),
  })),
);

const sangriaTotal = computed(() =>
  (report.value?.days ?? []).reduce((sum, day) => sum + day.sangria_q, 0),
);

// Gaveta por hora do dia, do log de eventos do PDV. Aberturas sem venda e
// destraves da trava juntos na barra; o destrave vai no detalhe porque é a
// exceção (gerente com PIN), e exceção se lê separada.
const drawerHourRows = computed(() =>
  (report.value?.drawer_by_hour ?? []).map((row) => ({
    label: `${String(row.hour).padStart(2, "0")}h`,
    value: row.drawer_openings + row.drawer_unlocks,
    display: formatInt(row.drawer_openings + row.drawer_unlocks),
    hint: [
      row.drawer_unlocks ? `${formatInt(row.drawer_unlocks)} destrave${row.drawer_unlocks === 1 ? "" : "s"} por gerente` : "",
      row.blocks ? `${formatInt(row.blocks)} vez${row.blocks === 1 ? "" : "es"} travado (${formatDuration(row.open_seconds)} de gaveta aberta)` : "",
    ].filter(Boolean).join(" · ") || undefined,
  })),
);

/** Segundos em linguagem de balcão: ninguém lê "184 s". */
function formatDuration(seconds: number): string {
  if (!seconds) return "0 s";
  if (seconds < 60) return `${seconds} s`;
  const min = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (min < 60) return rest ? `${min} min ${rest} s` : `${min} min`;
  return `${Math.floor(min / 60)} h ${min % 60} min`;
}

// A gaveta é o único lugar do caixa em que o SILÊNCIO é a informação: turno com
// dinheiro andando e nenhum bloqueio quer dizer que o sensor não estava falando.
// Por isso esta seção mostra ausência tanto quanto presença.
const drawerRows = computed(() => report.value?.drawer_by_operator ?? []);
const anomalies = computed(() => report.value?.drawer_anomalies ?? []);

// As duas tabelas do caixa são NuxtTable: cada uma é o corpo inteiro do quadro, e o
// tema do kit a integra ao cartão (sem padding, linhas de ponta a ponta). A coluna
// numérica alinha à direita; o tom de cada célula sai do valor (abaixo).
const NUM = { th: "text-right", td: "text-right tnum" } as const;
const operatorColumns = [
  { accessorKey: "operator", header: "Operador", meta: { class: { td: "font-medium text-foreground" } } },
  { id: "shifts", header: "Turnos", meta: { class: NUM } },
  { id: "difference", header: "Quebra", meta: { class: NUM } },
  { id: "drawer_openings", header: "Gaveta", meta: { class: NUM } },
  { id: "drawer_unlocks", header: "Destraves", meta: { class: NUM } },
  { id: "change_requests", header: "Troco", meta: { class: NUM } },
];
const drawerColumns = [
  { accessorKey: "operator", header: "Operador", meta: { class: { td: "font-medium text-foreground" } } },
  { id: "blocks", header: "Travou", meta: { class: NUM } },
  { id: "open_seconds", header: "Aberta (total)", meta: { class: NUM } },
  { id: "longest_open_seconds", header: "Pior episódio", meta: { class: NUM } },
  { id: "dismissals", header: "Desistiu", meta: { class: NUM } },
  { id: "overrides", header: "Destraves", meta: { class: NUM } },
  { id: "unlock_attempts", header: "Buscou o PIN", meta: { class: NUM } },
  { id: "sensor_blind", header: "Sensor mudo", meta: { class: NUM } },
  { id: "left_open", header: "Esquecida", meta: { class: NUM } },
];
/** Exceção acima de zero se lê: em negrito; zero recua. */
const exceptionTone = (value: number) => (value ? "font-semibold text-foreground" : "text-muted-foreground");
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="O caixa fechou certo?" eyebrow="Auditoria do Dono">
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
    </OperatorPageHeader>

    <main class="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
      <BiPageState :pending="pending && !report" :error="error" @retry="refresh()" />
      <template v-if="report">
        <!-- `xl:grid-cols-[1.4fr_1fr...]`: a resposta (uma frase) pede mais largura que cada número. -->
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
          <BiAnswer :text="cashAnswer(report)" class="col-span-2 xl:col-span-1" />
          <StatTile
            label="Turnos fechados"
            :value="formatInt(report.shifts_total)"
            :delta="delta(report.shifts_total, report.previous.shifts_total, { base: formatInt(report.previous.shifts_total) })"
          />
          <StatTile
            label="Quebra acumulada"
            :value="formatMoney(report.difference_total_q)"
            :tone="report.difference_total_q < 0 ? 'destructive' : undefined"
            :hint="`Contado menos esperado; negativo = faltou. Período anterior: ${formatMoney(report.previous.difference_total_q)}`"
          />
          <StatTile
            label="Dias sem fechamento"
            :value="formatInt(report.closings_missing)"
            :tone="report.closings_missing ? 'warning' : undefined"
            hint="Na janela; o mix de pagamento só cobre dias fechados"
          />
          <StatTile label="Sangrias" :value="formatMoney(sangriaTotal)" hint="Retiradas do caixa no período" />
        </div>

        <BiSection title="Quebra de caixa por dia" caption="Acima do zero sobrou; abaixo faltou">
          <ChartDivergingBars :points="differenceSeries" :format="formatMoney" />
        </BiSection>

        <!-- Conta do cliente: só quando existe (dado opcional faz a tela crescer).
             Dívida nova e acerto na janela; saldo em aberto é de HOJE, derivado. -->
        <BiSection
          v-if="report.accounts.sales_q || report.accounts.settled_q || report.accounts.open_q"
          title="Contas na casa"
          caption="Vendas em conta e acertos no período; saldo em aberto é o de hoje"
          data-house-accounts
        >
          <div class="grid gap-3 sm:grid-cols-3">
            <StatTile label="Vendido em conta" :value="formatMoney(report.accounts.sales_q)" hint="Virou dívida no período" />
            <StatTile
              label="Acertado"
              :value="formatMoney(report.accounts.settled_q)"
              :hint="`Em dinheiro ${formatMoney(report.accounts.settled_cash_q)}`"
            />
            <StatTile
              label="Em aberto hoje"
              :value="formatMoney(report.accounts.open_q)"
              :hint="`${formatInt(report.accounts.open_customers)} ${report.accounts.open_customers === 1 ? 'cliente' : 'clientes'}`"
            />
          </div>
          <ul v-if="report.accounts.top_open.length" class="mt-3 grid gap-1 op-label">
            <li
              v-for="row in report.accounts.top_open"
              :key="row.customer_name"
              class="flex items-baseline justify-between border-b border-border py-1 last:border-0"
            >
              <span class="text-foreground">{{ row.customer_name }}</span>
              <span class="tnum text-foreground">{{ formatMoney(row.balance_q) }}</span>
            </li>
          </ul>
        </BiSection>

        <div class="grid gap-3 lg:grid-cols-2">
          <BiSection
            title="Por operador"
            caption="Quebra acumulada, aberturas de gaveta sem venda, destraves por gerente e pedidos de troco no período"
          >
            <NuxtTable
              v-if="report.by_operator.length"
              :data="report.by_operator"
              :columns="operatorColumns"
              :get-row-id="(row) => row.operator"
              caption="Caixa por operador"
              data-bi-cash-by-operator
            >
              <template #shifts-cell="{ row }">{{ formatInt(row.original.shifts) }}</template>
              <template #difference-cell="{ row }">
                <span :class="row.original.difference_q < 0 ? 'font-semibold text-destructive' : 'text-foreground'">{{ formatMoney(row.original.difference_q) }}</span>
              </template>
              <template #drawer_openings-cell="{ row }">{{ formatInt(row.original.drawer_openings) }}</template>
              <template #drawer_unlocks-cell="{ row }">
                <span :class="exceptionTone(row.original.drawer_unlocks)">{{ formatInt(row.original.drawer_unlocks) }}</span>
              </template>
              <template #change_requests-cell="{ row }">{{ formatInt(row.original.change_requests) }}</template>
            </NuxtTable>
            <p v-else class="op-body text-muted-foreground">Nenhum turno fechado nem evento de caixa no período.</p>
          </BiSection>
          <!-- O que a trava da gaveta revelou. Aqui a AUSÊNCIA é dado: um turno com
               dinheiro andando e zero bloqueio não é um balcão caprichoso, é um
               sensor que não estava falando com o PDV. -->
          <NuxtAlert
            v-if="anomalies.length"
            color="warning"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            title="Gaveta · o que pede explicação"
            data-bi-drawer-anomalies
          >
            <template #description>
              <p class="mb-2">Não é acusação: é onde olhar. Cada linha aponta um turno e diz o que não fecha.</p>
              <ul class="flex flex-col gap-1.5">
                <li v-for="(item, i) in anomalies" :key="`${item.code}-${item.shift_key}-${i}`" class="text-foreground">
                  <span class="font-semibold">{{ item.operator }}</span>
                  <span class="text-muted-foreground"> · turno {{ item.shift_key }} · </span>{{ item.detail }}
                </li>
              </ul>
            </template>
          </NuxtAlert>

          <BiSection
            title="Gaveta por operador"
            caption="Quantas vezes a trava agiu, quanto tempo a gaveta ficou aberta somada, e o pior episódio, que a média esconde. Desistir da venda em vez de fechar a gaveta, destrave e tentativa de PIN são exceção: qualquer número acima de zero se lê."
          >
            <NuxtTable
              v-if="drawerRows.length"
              :data="drawerRows"
              :columns="drawerColumns"
              :get-row-id="(row) => row.operator"
              caption="Gaveta por operador"
              data-bi-drawer-by-operator
            >
              <template #blocks-cell="{ row }">{{ formatInt(row.original.blocks) }}</template>
              <template #open_seconds-cell="{ row }">{{ formatDuration(row.original.open_seconds) }}</template>
              <template #longest_open_seconds-cell="{ row }">{{ formatDuration(row.original.longest_open_seconds) }}</template>
              <template #dismissals-cell="{ row }"><span :class="exceptionTone(row.original.dismissals)">{{ formatInt(row.original.dismissals) }}</span></template>
              <template #overrides-cell="{ row }"><span :class="exceptionTone(row.original.overrides)">{{ formatInt(row.original.overrides) }}</span></template>
              <template #unlock_attempts-cell="{ row }"><span :class="exceptionTone(row.original.unlock_attempts)">{{ formatInt(row.original.unlock_attempts) }}</span></template>
              <template #sensor_blind-cell="{ row }">
                <span :class="row.original.sensor_blind ? 'font-semibold text-destructive' : 'text-muted-foreground'">{{ formatInt(row.original.sensor_blind) }}</span>
              </template>
              <template #left_open-cell="{ row }"><span :class="exceptionTone(row.original.left_open)">{{ formatInt(row.original.left_open) }}</span></template>
            </NuxtTable>
            <p v-else class="op-body text-muted-foreground">
              Nenhum episódio de gaveta no período. Num balcão com sensor armado e movimento, isso merece conferência.
            </p>
          </BiSection>

          <BiSection title="Meios de pagamento" caption="Consolidado dos fechamentos do período">
            <ChartHBarList v-if="methodRows.length" :rows="methodRows" />
            <p v-else class="op-body text-muted-foreground">Nenhum fechamento na janela ainda.</p>
          </BiSection>
        </div>

        <BiSection title="Gaveta por hora do dia" caption="Aberturas sem venda e destraves da trava, do log de eventos do PDV">
          <ChartHBarList v-if="drawerHourRows.length" :rows="drawerHourRows" />
          <p v-else class="op-body text-muted-foreground">Nenhuma abertura de gaveta sem venda no período.</p>
        </BiSection>
      </template>
      <BiSwipeHint />
    </main>
  </div>
</template>
