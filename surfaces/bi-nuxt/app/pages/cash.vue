<script setup lang="ts">
// Caixa — quebra por dia e por operador, sangrias/suprimentos e o mix de
// pagamento consolidado pelo fechamento. `closings_missing` fica à vista:
// buraco declarado, nunca silenciado.
//
// Esta tela é a AUDITORIA DO DONO: o endpoint exige `cashman.audit_shift`, que só o
// grupo Dono concede. A decisão do fechamento às cegas (SUITE-UX §15: "o número só
// existe na auditoria do Dono") é o que permite o valor aqui e em nenhum outro lugar;
// o cabeçalho diz isso em vez de deixar o leitor adivinhar por que vê R$.
//
// Peças do kit (PR-B4 do WP-BI-CANON-LAUDO): os números da página são `OperatorMetric`;
// cada quadro é um `OperatorReadingCard` (com o ⋯ "Exportar CSV deste quadro"); os
// gráficos são `OperatorReadingChart`; listas são `NuxtTable` e vazio é `NuxtEmpty`.
// Cartão dentro de cartão só `soft` (as três contas da casa).
import type { BICashReport } from "~/types/bi";
import { cashAnswer, delta, formatInt, formatMoney } from "~/presentation/bi";
import {
  CASH_DIFFERENCE_SERIES,
  CASH_DIFFERENCE_SIDES,
  DRAWER_HOUR_CSV_SERIES,
  DRAWER_HOUR_SERIES,
  cashDifferenceAxis,
  cashDifferencePoints,
  cashMethodRows,
  drawerCsv,
  drawerHourPoints,
  formatDuration,
  methodsCsv,
  openAccountsCsv,
  operatorCsv,
} from "~/presentation/cash";
import { readingChartCsv } from "../../../operator-kit/app/presentation/readingChart";

const { report, pending, error, refresh } = useBiReport<BICashReport>("cash");

// O relatório do caixa não traz `generated_at`: a hora da leitura é a de quando ela
// chegou a este dispositivo. Por isso a frase só existe no cliente (`ClientOnly`):
// no SSR o servidor não sabe quando a página vai hidratar. Cada leitura nova, de
// período trocado ou de "Tentar de novo", carimba de novo.
const readAt = ref("");
onMounted(() => {
  watch(
    report,
    (value) => {
      if (value) readAt.value = new Date().toISOString();
    },
    { immediate: true },
  );
});
const freshness = computed(() => ({ generated_at: readAt.value || null }));

const days = computed(() => report.value?.days ?? []);
const differencePoints = computed(() => cashDifferencePoints(days.value));
const differenceAxis = computed(() => cashDifferenceAxis(days.value));
const differenceCsv = computed(() =>
  readingChartCsv(differenceAxis.value, CASH_DIFFERENCE_SERIES, differencePoints.value),
);

const sangriaTotal = computed(() => days.value.reduce((sum, day) => sum + day.sangria_q, 0));

const methodRows = computed(() => cashMethodRows(report.value?.payment_methods ?? []));

// Gaveta por hora do dia, do log de eventos do PDV. Aberturas sem venda e destraves
// lado a lado; o destrave em outra cor porque é a exceção (gerente com PIN).
const hourPoints = computed(() => drawerHourPoints(report.value?.drawer_by_hour ?? []));
const hourCsv = computed(() => readingChartCsv("Hora", DRAWER_HOUR_CSV_SERIES, hourPoints.value));

// A gaveta é o único lugar do caixa em que o SILÊNCIO é a informação: turno com
// dinheiro andando e nenhum bloqueio quer dizer que o sensor não estava falando.
// Por isso esta seção mostra ausência tanto quanto presença.
const drawerRows = computed(() => report.value?.drawer_by_operator ?? []);
const anomalies = computed(() => report.value?.drawer_anomalies ?? []);

const hasAccounts = computed(() => {
  const accounts = report.value?.accounts;
  return Boolean(accounts && (accounts.sales_q || accounts.settled_q || accounts.open_q));
});

// As tabelas do caixa são NuxtTable: cada uma é o corpo inteiro do quadro, e o tema do
// kit a integra ao cartão (sem padding, linhas de ponta a ponta). A coluna numérica
// alinha à direita; o tom de cada célula sai do valor (abaixo).
const NUM = { th: "text-right", td: "text-right tnum" } as const;
const NAME = { td: "font-medium text-highlighted" } as const;
const operatorColumns = [
  { accessorKey: "operator", header: "Operador", meta: { class: NAME } },
  { id: "shifts", header: "Turnos", meta: { class: NUM } },
  { id: "difference", header: "Quebra", meta: { class: NUM } },
  { id: "drawer_openings", header: "Gaveta", meta: { class: NUM } },
  { id: "drawer_unlocks", header: "Destraves", meta: { class: NUM } },
  { id: "change_requests", header: "Troco", meta: { class: NUM } },
];
const drawerColumns = [
  { accessorKey: "operator", header: "Operador", meta: { class: NAME } },
  { id: "blocks", header: "Travou", meta: { class: NUM } },
  { id: "open_seconds", header: "Aberta (total)", meta: { class: NUM } },
  { id: "longest_open_seconds", header: "Pior episódio", meta: { class: NUM } },
  { id: "dismissals", header: "Desistiu", meta: { class: NUM } },
  { id: "overrides", header: "Destraves", meta: { class: NUM } },
  { id: "unlock_attempts", header: "Buscou o PIN", meta: { class: NUM } },
  { id: "sensor_blind", header: "Sensor mudo", meta: { class: NUM } },
  { id: "left_open", header: "Esquecida", meta: { class: NUM } },
];
const methodColumns = [
  { accessorKey: "method", header: "Meio", meta: { class: NAME } },
  { id: "amount", header: "Valor", meta: { class: NUM } },
  { id: "share", header: "Fatia" },
];
const accountColumns = [
  { accessorKey: "customer_name", header: "Cliente", meta: { class: NAME } },
  { id: "balance", header: "Em aberto", meta: { class: NUM } },
];
/** Exceção acima de zero se lê: em negrito; zero recua. */
const exceptionTone = (value: number) => (value ? "font-semibold text-highlighted" : "text-muted");
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="O caixa fechou certo?" eyebrow="Auditoria do Dono">
      <template #actions>
        <OperatorReadingPageMenu />
      </template>
      <!-- A linha de recortes, como no Histórico do Gestor: o período e, no fim, o
           frescor da leitura. No celular a barra de cima não comporta o período. -->
      <template #filters>
        <BiWindowPicker compact align="start" />
        <ClientOnly><ReadFreshness inline :metadata="freshness" :failed="Boolean(error)" /></ClientOnly>
      </template>
    </OperatorPageHeader>

    <!-- Bloco, não coluna flex: o cartão do Nuxt UI corta o que passa (overflow), e
         numa coluna flex que rola ele encolhia até sumir (o gráfico e as contas da
         casa viravam uma linha). Cada quadro tem a altura do próprio conteúdo. -->
    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <NuxtEmpty
        v-if="pending && !report"
        loading
        icon="i-lucide-wallet"
        title="Lendo o caixa do período"
        description="Turnos, quebra, gaveta e meios de pagamento."
        data-bi-loading
      />
      <BiPageState v-else :error="error" what="o caixa" @retry="refresh()" />

      <template v-if="report">
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-5">
          <OperatorMetric
            title="A resposta"
            :value="cashAnswer(report)"
            size="statement"
            class="col-span-2 xl:col-span-1"
            data-bi-answer
          />
          <OperatorMetric
            title="Turnos fechados"
            :value="formatInt(report.shifts_total)"
            :delta="delta(report.shifts_total, report.previous.shifts_total, { base: formatInt(report.previous.shifts_total) })"
          />
          <OperatorMetric
            title="Quebra acumulada"
            :value="formatMoney(report.difference_total_q)"
            :tone="report.difference_total_q < 0 ? 'error' : undefined"
            :hint="`Contado menos esperado; negativo = faltou. Período anterior: ${formatMoney(report.previous.difference_total_q)}`"
          />
          <OperatorMetric
            title="Dias sem fechamento"
            :value="formatInt(report.closings_missing)"
            :tone="report.closings_missing ? 'warning' : undefined"
            hint="Na janela; o mix de pagamento só cobre dias fechados"
          />
          <OperatorMetric title="Sangrias" :value="formatMoney(sangriaTotal)" hint="Retiradas do caixa no período" />
        </div>

        <OperatorReadingCard
          title="Quebra de caixa por dia"
          description="Acima do zero sobrou; abaixo faltou"
          :csv="differencePoints.length ? differenceCsv : undefined"
        >
          <OperatorReadingChart
            title="Quebra de caixa por dia"
            kind="diverging"
            :axis-label="differenceAxis"
            :series="CASH_DIFFERENCE_SERIES"
            :points="differencePoints"
            :diverging="CASH_DIFFERENCE_SIDES"
            :format="formatMoney"
            empty-title="Nenhum turno fechado no período"
            empty-description="Sem fechamento não há quebra para medir."
          />
        </OperatorReadingCard>

        <!-- Conta do cliente: só quando existe (dado opcional faz a tela crescer).
             Dívida nova e acerto na janela; saldo em aberto é de HOJE, derivado.
             As três contas são cartões `soft` dentro do quadro: um nível de borda só. -->
        <OperatorReadingCard
          v-if="hasAccounts"
          title="Contas na casa"
          description="Vendas em conta e acertos no período; saldo em aberto é o de hoje"
          :csv="report.accounts.top_open.length ? openAccountsCsv(report.accounts.top_open) : undefined"
          data-house-accounts
        >
          <div class="grid gap-3 sm:grid-cols-3">
            <OperatorMetric
              variant="soft"
              title="Vendido em conta"
              :value="formatMoney(report.accounts.sales_q)"
              hint="Virou dívida no período"
            />
            <OperatorMetric
              variant="soft"
              title="Acertado"
              :value="formatMoney(report.accounts.settled_q)"
              :hint="`Em dinheiro ${formatMoney(report.accounts.settled_cash_q)}`"
            />
            <OperatorMetric
              variant="soft"
              title="Em aberto hoje"
              :value="formatMoney(report.accounts.open_q)"
              :hint="`${formatInt(report.accounts.open_customers)} ${report.accounts.open_customers === 1 ? 'cliente' : 'clientes'}`"
            />
          </div>
          <NuxtTable
            v-if="report.accounts.top_open.length"
            :data="report.accounts.top_open"
            :columns="accountColumns"
            :get-row-id="(row) => row.customer_name"
            caption="Clientes com conta em aberto"
            class="mt-3"
            data-bi-open-accounts
          >
            <template #balance-cell="{ row }">{{ formatMoney(row.original.balance_q) }}</template>
          </NuxtTable>
        </OperatorReadingCard>

        <div class="grid items-start gap-3 lg:grid-cols-2">
          <OperatorReadingCard
            title="Por operador"
            description="Quebra acumulada, aberturas de gaveta sem venda, destraves por gerente e pedidos de troco no período"
            :csv="report.by_operator.length ? operatorCsv(report.by_operator) : undefined"
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
                <span :class="row.original.difference_q < 0 ? 'font-semibold text-error' : 'text-highlighted'">{{ formatMoney(row.original.difference_q) }}</span>
              </template>
              <template #drawer_openings-cell="{ row }">{{ formatInt(row.original.drawer_openings) }}</template>
              <template #drawer_unlocks-cell="{ row }">
                <span :class="exceptionTone(row.original.drawer_unlocks)">{{ formatInt(row.original.drawer_unlocks) }}</span>
              </template>
              <template #change_requests-cell="{ row }">{{ formatInt(row.original.change_requests) }}</template>
            </NuxtTable>
            <NuxtEmpty
              v-else
              variant="naked"
              icon="i-lucide-users"
              title="Nenhum turno fechado nem evento de caixa no período"
            />
          </OperatorReadingCard>

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
                <li v-for="(item, i) in anomalies" :key="`${item.code}-${item.shift_key}-${i}`" class="text-highlighted">
                  <span class="font-semibold">{{ item.operator }}</span>
                  <span class="text-muted"> · turno {{ item.shift_key }} · </span>{{ item.detail }}
                </li>
              </ul>
            </template>
          </NuxtAlert>

          <OperatorReadingCard
            title="Gaveta por operador"
            description="Quantas vezes a trava agiu, quanto tempo a gaveta ficou aberta somada, e o pior episódio, que a média esconde. Desistir da venda em vez de fechar a gaveta, destrave e tentativa de PIN são exceção: qualquer número acima de zero se lê."
            :csv="drawerRows.length ? drawerCsv(drawerRows) : undefined"
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
                <span :class="row.original.sensor_blind ? 'font-semibold text-error' : 'text-muted'">{{ formatInt(row.original.sensor_blind) }}</span>
              </template>
              <template #left_open-cell="{ row }"><span :class="exceptionTone(row.original.left_open)">{{ formatInt(row.original.left_open) }}</span></template>
            </NuxtTable>
            <NuxtEmpty
              v-else
              variant="naked"
              icon="i-lucide-archive"
              title="Nenhum episódio de gaveta no período"
              description="Num balcão com sensor armado e movimento, isso merece conferência."
            />
          </OperatorReadingCard>

          <OperatorReadingCard
            title="Meios de pagamento"
            description="Consolidado dos fechamentos do período"
            :csv="methodRows.length ? methodsCsv(methodRows) : undefined"
          >
            <NuxtTable
              v-if="methodRows.length"
              :data="methodRows"
              :columns="methodColumns"
              :get-row-id="(row) => row.method"
              caption="Meios de pagamento no período"
              data-bi-payment-methods
            >
              <template #amount-cell="{ row }">{{ formatMoney(row.original.amount_q) }}</template>
              <template #share-cell="{ row }">
                <span class="flex min-w-24 items-center gap-2">
                  <NuxtProgress :model-value="row.original.share" class="flex-1" aria-hidden="true" />
                  <span class="tnum">{{ row.original.shareLabel }}</span>
                </span>
              </template>
            </NuxtTable>
            <NuxtEmpty
              v-else
              variant="naked"
              icon="i-lucide-credit-card"
              title="Nenhum fechamento na janela ainda"
              description="O mix de pagamento sai do fechamento do caixa."
            />
          </OperatorReadingCard>
        </div>

        <OperatorReadingCard
          title="Gaveta por hora do dia"
          description="Aberturas sem venda e destraves da trava, do log de eventos do PDV"
          :csv="hourPoints.length ? hourCsv : undefined"
        >
          <OperatorReadingChart
            title="Gaveta por hora do dia"
            axis-label="Hora"
            :series="DRAWER_HOUR_SERIES"
            :points="hourPoints"
            empty-title="Nenhuma abertura de gaveta sem venda no período"
          />
        </OperatorReadingCard>
      </template>
    </main>
  </div>
</template>
