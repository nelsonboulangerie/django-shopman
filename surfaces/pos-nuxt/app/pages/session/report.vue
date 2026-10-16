<script setup lang="ts">
import type { OperatorHeaderAction } from "../../../../operator-kit/app/presentation/pageHeader";

// RELATÓRIO da sessão de caixa na antesala (WP-ADM-4, benchmark Odoo POS):
// leitura X (parcial do turno ABERTO do operador), leituras Z (turnos
// FECHADOS do dia) e o histórico agregado de turnos/vendas. Read-only sobre
// GET /api/v1/backstage/pos/cash/report/, gate `cashman.operate_pos`.
// BLIND: o PDV nunca mostra o valor ESPERADO da gaveta nem a variância — a
// conferência (esperado vs contado) é da retaguarda. Impressão térmica fica
// fora (capítulo NFC-e).
useHead({ title: "Relatório de caixa" });

const action = usePosAction();
// A projection do terminal entra por dois motivos: o `terminal_ref` prende a
// leitura X à GAVETA desta superfície (sem ele o servidor cai no primeiro
// terminal ativo), e o write-side da sessão dá a porta da segunda via do
// comprovante de movimento.
const { pos, actions, refresh: refreshPos } = await usePosTerminal();
const { report, pending, accessDenied, stationRefusal, refresh } = await useCashReport({
  terminalRef: () => pos.value?.terminal_ref || "",
});
const { busy, canPrintReceipt, reprintMovementReceipt } = usePosCashSession({
  pos,
  actions,
  refresh: refreshPos,
  action,
});

// A segunda via só é oferecida onde existe caminho de impressão (agente do
// balcão). Num terminal sem agente o botão seria porta que bate na cara.
// É a IMPRESSORA que responde por isto, não a gaveta: este botão sumia no
// balcão que tem bobina e abre a gaveta com a chave.
const canReprint = computed(() => canPrintReceipt.value === true);

function reprint(entryId: number) {
  void reprintMovementReceipt(entryId);
}

// A volta à Sessão de caixa é um link (`to`), não um clique que navega: sem espera
// para declarar, e o endereço aparece no toque longo.

const NUM = { class: { th: "text-right", td: "text-right tabular-nums whitespace-nowrap" } };
const dayMethodColumns = [
  { accessorKey: "method_label", header: "Método" },
  { accessorKey: "orders_count", header: "Pagamentos", meta: NUM },
  { id: "amount", header: "Valor", meta: NUM },
];

const headerActions = computed<OperatorHeaderAction[]>(() => [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", priority: 1, disabled: pending.value, onSelect: () => void refresh() },
]);
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <!-- O cabeçalho da suíte, no papel de corredor (WP-FASE2 §6, K6): voltar ao Caixa,
         o título, o dia e o Atualizar no ⋯; sem campo de busca, sem Avisos, sem navegação.
         ⚠️ O kit não tem a variante `task` do cabeçalho: o corredor é o cabeçalho comum
         com `:inbox="false"` e a busca só no atalho. -->
    <OperatorPageHeader title="Relatório de caixa" :inbox="false" :actions="headerActions" actions-label="Mais ações do relatório">
      <!-- A busca da suíte só no Ctrl K (e na lupa do celular): no corredor não há campo
           de busca na tela, e o "/" não tira a pessoa da contagem. -->
      <template #search>
        <OperatorSuiteSearch variant="hotkey" placeholder="Buscar pedido, cliente, produto ou tela" />
      </template>
      <template #lead>
        <NuxtButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-arrow-left"
          square
          to="/session"
          aria-label="Voltar à sessão de caixa"
          title="Sessão de caixa"
          data-report-back
        />
      </template>
      <template v-if="report" #status>
        <span class="text-xs text-muted-foreground">{{ report.date_display }} · leituras X/Z do dia</span>
      </template>
    </OperatorPageHeader>

    <div class="mx-auto grid w-full max-w-2xl gap-6 p-4 md:py-8">
      <!-- Sem permissão de operação do PDV. -->
      <OperatorScreenState
        v-if="accessDenied"
        state="empty"
        icon="i-lucide-lock"
        title="Relatório é de quem audita"
        description="Esta tela mostra o faturamento do dia. Sua conta opera o caixa, mas não audita: quem vê a apuração é a gestão."
      >
        <template #actions>
          <NuxtButton color="neutral" variant="outline" icon="i-lucide-arrow-left" label="Voltar à sessão de caixa" to="/session" />
        </template>
      </OperatorScreenState>

      <!-- Balcão errado (409 da estação): o operador precisa saber ONDE está. -->
      <OperatorScreenState
        v-else-if="stationRefusal"
        state="empty"
        icon="i-lucide-monitor-x"
        :title="stationRefusal.title"
        :description="stationRefusal.message"
        data-station-refusal
      >
        <template #actions>
          <NuxtButton color="neutral" variant="outline" icon="i-lucide-arrow-left" label="Voltar à sessão de caixa" to="/session" />
        </template>
      </OperatorScreenState>

      <template v-else-if="report">
        <!-- Leitura X: parcial do turno aberto do operador. -->
        <PosCashReadingCard
          v-if="report.x_reading"
          :reading="report.x_reading"
          :can-reprint="canReprint"
          :busy="busy"
          @reprint="reprint"
        />
        <section v-else class="grid gap-2" aria-labelledby="x-reading-empty">
          <div class="flex items-center gap-2">
            <Icon name="lucide:receipt-text" class="size-4 text-muted-foreground" />
            <h2 id="x-reading-empty" class="text-base font-semibold">Leitura X</h2>
          </div>
          <p class="text-sm text-muted-foreground">
            Sem turno aberto neste terminal. Abra o caixa na sessão para acompanhar a parcial do turno.
          </p>
        </section>

        <!-- Leituras Z: turnos fechados hoje. -->
        <template v-if="report.has_closed_shifts">
          <PosCashReadingCard
            v-for="reading in report.z_readings"
            :key="reading.shift_id"
            :reading="reading"
            :can-reprint="canReprint"
            :busy="busy"
            @reprint="reprint"
          />
        </template>
        <section v-else class="grid gap-2" aria-labelledby="z-reading-empty">
          <div class="flex items-center gap-2">
            <Icon name="lucide:archive" class="size-4 text-muted-foreground" />
            <h2 id="z-reading-empty" class="text-base font-semibold">Leituras Z</h2>
          </div>
          <p class="text-sm text-muted-foreground">Nenhum turno fechado hoje.</p>
        </section>

        <!-- Histórico do dia: totais agregados dos turnos fechados. -->
        <section v-if="report.has_closed_shifts" class="grid gap-3" aria-labelledby="day-history-title" data-day-history>
          <div class="flex items-center gap-2">
            <Icon name="lucide:history" class="size-4 text-muted-foreground" />
            <h2 id="day-history-title" class="text-base font-semibold">Histórico do dia</h2>
          </div>
          <NuxtCard>
            <dl class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div class="flex flex-col">
                <dt class="text-xs text-muted-foreground">Turnos fechados</dt>
                <dd class="font-medium tabular-nums">{{ report.day_totals.shifts_count }}</dd>
              </div>
              <div class="flex flex-col">
                <dt class="text-xs text-muted-foreground">Vendas</dt>
                <dd class="font-medium tabular-nums">{{ report.day_totals.sales_count }}</dd>
              </div>
              <div class="flex flex-col">
                <dt class="text-xs text-muted-foreground">Total vendido</dt>
                <dd class="font-medium tabular-nums">R$ {{ report.day_totals.sales_total_display }}</dd>
              </div>
              <div class="flex flex-col">
                <dt class="text-xs text-muted-foreground">Total contado</dt>
                <dd class="font-medium tabular-nums">R$ {{ report.day_totals.counted_total_display }}</dd>
              </div>
            </dl>
          </NuxtCard>
          <OperatorTable
            v-if="report.day_totals.sales_by_method.length"
            :data="report.day_totals.sales_by_method"
            :columns="dayMethodColumns"
            :row-key="(row) => row.method"
            caption="Vendas do dia por método"
          >
            <template #amount-cell="{ row }">R$ {{ row.original.amount_display }}</template>
          </OperatorTable>
          <p class="text-xs text-muted-foreground">
            A conferência do contado com o esperado fica na retaguarda.
          </p>
        </section>
      </template>

      <OperatorScreenState v-else-if="pending" state="loading" what="o relatório de caixa" />
    </div>
  </main>
</template>
