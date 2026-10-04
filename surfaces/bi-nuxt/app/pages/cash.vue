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
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="O caixa fechou certo?" eyebrow="Auditoria do Dono">
      <template #actions>
        <BiWindowPicker />
        <BiPageMenu />
      </template>
    </OperatorPageHeader>

    <main class="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
      <BiPageState :pending="pending && !report" :error="error" @retry="refresh()" />
      <template v-if="report">
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
          <BiAnswer :text="cashAnswer(report)" class="col-span-2 xl:col-span-1" />
          <StatTile
            label="Turnos fechados"
            :value="formatInt(report.shifts_total)"
            :delta="delta(report.shifts_total, report.previous.shifts_total)"
          />
          <StatTile
            label="Quebra acumulada"
            :value="formatMoney(report.difference_total_q)"
            :tone="report.difference_total_q < 0 ? 'destructive' : undefined"
            :delta="{ text: `Anterior ${formatMoney(report.previous.difference_total_q)}`, tone: 'neutral' }"
            hint="Contado − esperado; negativo = faltou"
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
            <div class="overflow-x-auto">
              <table v-if="report.by_operator.length" class="w-full op-label">
                <thead>
                  <tr class="border-b border-border text-left op-eyebrow text-muted-foreground">
                    <th class="pb-2 font-semibold">Operador</th>
                    <th class="pb-2 text-right font-semibold">Turnos</th>
                    <th class="pb-2 text-right font-semibold">Quebra</th>
                    <th class="pb-2 text-right font-semibold">Gaveta</th>
                    <th class="pb-2 text-right font-semibold">Destraves</th>
                    <th class="pb-2 text-right font-semibold">Troco</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in report.by_operator" :key="row.operator" class="border-b border-border last:border-0">
                    <td class="py-2 pr-2 font-medium text-foreground">{{ row.operator }}</td>
                    <td class="py-2 text-right tnum text-foreground">{{ formatInt(row.shifts) }}</td>
                    <td
                      class="py-2 text-right tnum"
                      :class="row.difference_q < 0 ? 'font-semibold text-destructive' : 'text-foreground'"
                    >
                      {{ formatMoney(row.difference_q) }}
                    </td>
                    <td class="py-2 text-right tnum text-foreground">{{ formatInt(row.drawer_openings) }}</td>
                    <td
                      class="py-2 text-right tnum"
                      :class="row.drawer_unlocks ? 'font-semibold text-foreground' : 'text-muted-foreground'"
                    >
                      {{ formatInt(row.drawer_unlocks) }}
                    </td>
                    <td class="py-2 text-right tnum text-foreground">{{ formatInt(row.change_requests) }}</td>
                  </tr>
                </tbody>
              </table>
              <p v-else class="op-body text-muted-foreground">Nenhum turno fechado nem evento de caixa no período.</p>
            </div>
          </BiSection>
          <!-- O que a trava da gaveta revelou. Aqui a AUSÊNCIA é dado: um turno com
               dinheiro andando e zero bloqueio não é um balcão caprichoso, é um
               sensor que não estava falando com o PDV. -->
          <section v-if="anomalies.length" class="rounded-lg border border-warning/40 bg-warning/5 px-4 py-3">
            <h2 class="op-title text-foreground">Gaveta · o que pede explicação</h2>
            <p class="mb-3 op-micro text-muted-foreground">
              Não é acusação: é onde olhar. Cada linha aponta um turno e diz o que não fecha.
            </p>
            <ul class="flex flex-col gap-2">
              <li v-for="(item, i) in anomalies" :key="`${item.code}-${item.shift_key}-${i}`" class="flex gap-2 op-label">
                <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
                <span class="text-foreground">
                  <span class="font-semibold">{{ item.operator }}</span>
                  <span class="text-muted-foreground"> · turno {{ item.shift_key }} · </span>{{ item.detail }}
                </span>
              </li>
            </ul>
          </section>

          <BiSection
            title="Gaveta por operador"
            caption="Quantas vezes a trava agiu, quanto tempo a gaveta ficou aberta somada, e o pior episódio, que a média esconde. Desistir da venda em vez de fechar a gaveta, destrave e tentativa de PIN são exceção: qualquer número acima de zero se lê."
          >
            <div class="overflow-x-auto">
              <table v-if="drawerRows.length" class="w-full min-w-160 op-label">
                <thead>
                  <tr class="border-b border-border text-left op-eyebrow text-muted-foreground">
                    <th class="pb-2 font-semibold">Operador</th>
                    <th class="pb-2 text-right font-semibold">Travou</th>
                    <th class="pb-2 text-right font-semibold">Aberta (total)</th>
                    <th class="pb-2 text-right font-semibold">Pior episódio</th>
                    <th class="pb-2 text-right font-semibold">Desistiu</th>
                    <th class="pb-2 text-right font-semibold">Destraves</th>
                    <th class="pb-2 text-right font-semibold">Buscou o PIN</th>
                    <th class="pb-2 text-right font-semibold">Sensor mudo</th>
                    <th class="pb-2 text-right font-semibold">Esquecida</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in drawerRows" :key="row.operator" class="border-b border-border last:border-0">
                    <td class="py-2 pr-2 font-medium text-foreground">{{ row.operator }}</td>
                    <td class="py-2 text-right tnum text-foreground">{{ formatInt(row.blocks) }}</td>
                    <td class="py-2 text-right tnum text-foreground">{{ formatDuration(row.open_seconds) }}</td>
                    <td class="py-2 text-right tnum text-foreground">{{ formatDuration(row.longest_open_seconds) }}</td>
                    <td class="py-2 text-right tnum" :class="row.dismissals ? 'font-semibold text-foreground' : 'text-muted-foreground'">{{ formatInt(row.dismissals) }}</td>
                    <td class="py-2 text-right tnum" :class="row.overrides ? 'font-semibold text-foreground' : 'text-muted-foreground'">{{ formatInt(row.overrides) }}</td>
                    <td class="py-2 text-right tnum" :class="row.unlock_attempts ? 'font-semibold text-foreground' : 'text-muted-foreground'">{{ formatInt(row.unlock_attempts) }}</td>
                    <td class="py-2 text-right tnum" :class="row.sensor_blind ? 'font-semibold text-destructive' : 'text-muted-foreground'">{{ formatInt(row.sensor_blind) }}</td>
                    <td class="py-2 text-right tnum" :class="row.left_open ? 'font-semibold text-foreground' : 'text-muted-foreground'">{{ formatInt(row.left_open) }}</td>
                  </tr>
                </tbody>
              </table>
              <p v-else class="op-body text-muted-foreground">
                Nenhum episódio de gaveta no período. Num balcão com sensor armado e movimento, isso merece conferência.
              </p>
            </div>
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
    </main>
  </div>
</template>
