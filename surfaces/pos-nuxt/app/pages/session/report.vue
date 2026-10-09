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

async function goToCashSession() {
  await navigateTo("/session");
}

const headerActions = computed<OperatorHeaderAction[]>(() => [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", priority: 1, disabled: pending.value, onSelect: () => void refresh() },
]);
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <!-- O cabeçalho da suíte, no papel de corredor (WP-FASE2 §6, K6): voltar ao Caixa,
         o título, o dia e o Atualizar no ⋯; sem campo de busca, sem Avisos, sem navegação. -->
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
          aria-label="Voltar à sessão de caixa"
          title="Sessão de caixa"
          data-report-back
          @click="goToCashSession"
        />
      </template>
      <template v-if="report" #status>
        <span class="text-xs text-muted-foreground">{{ report.date_display }} · leituras X/Z do dia</span>
      </template>
    </OperatorPageHeader>

    <div class="mx-auto grid w-full max-w-2xl gap-4 p-4 md:py-8">
      <!-- Sem permissão de operação do PDV. -->
      <section v-if="accessDenied" class="grid gap-2 rounded-md border bg-card p-4">
        <div class="flex items-center gap-2">
          <Icon name="lucide:lock" class="size-4 text-muted-foreground" />
          <h2 class="text-base font-semibold">Relatório é de quem audita</h2>
        </div>
        <p class="text-sm text-muted-foreground">
          Esta tela mostra o faturamento do dia. Sua conta opera o caixa, mas não audita: quem vê a
          apuração é a gestão.
        </p>
        <UiButton variant="outline" size="sm" @click="goToCashSession">Voltar à sessão de caixa</UiButton>
      </section>

      <!-- Balcão errado (409 da estação): o operador precisa saber ONDE está. -->
      <section v-else-if="stationRefusal" class="grid gap-2 rounded-md border bg-card p-4" data-station-refusal>
        <div class="flex items-center gap-2">
          <Icon name="lucide:monitor-x" class="size-4 text-warning" />
          <h2 class="text-base font-semibold">{{ stationRefusal.title }}</h2>
        </div>
        <p class="text-sm text-muted-foreground">{{ stationRefusal.message }}</p>
        <UiButton variant="outline" size="sm" @click="goToCashSession">Voltar à sessão de caixa</UiButton>
      </section>

      <template v-else-if="report">
        <!-- Leitura X: parcial do turno aberto do operador. -->
        <PosCashReadingCard
          v-if="report.x_reading"
          :reading="report.x_reading"
          :can-reprint="canReprint"
          :busy="busy"
          @reprint="reprint"
        />
        <section v-else class="grid gap-2 rounded-md border bg-card p-4">
          <div class="flex items-center gap-2">
            <Icon name="lucide:receipt-text" class="size-4 text-muted-foreground" />
            <h2 class="text-base font-semibold">Leitura X</h2>
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
        <section v-else class="grid gap-2 rounded-md border bg-card p-4">
          <div class="flex items-center gap-2">
            <Icon name="lucide:archive" class="size-4 text-muted-foreground" />
            <h2 class="text-base font-semibold">Leituras Z</h2>
          </div>
          <p class="text-sm text-muted-foreground">Nenhum turno fechado hoje.</p>
        </section>

        <!-- Histórico do dia: totais agregados dos turnos fechados. -->
        <section v-if="report.has_closed_shifts" class="grid gap-2 rounded-md border bg-card p-4">
          <div class="flex items-center gap-2">
            <Icon name="lucide:history" class="size-4 text-muted-foreground" />
            <h2 class="text-base font-semibold">Histórico do dia</h2>
          </div>
          <div class="grid grid-cols-2 gap-2 rounded-md border bg-muted/40 p-3 text-sm sm:grid-cols-4">
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Turnos fechados</span>
              <span class="font-medium tabular-nums">{{ report.day_totals.shifts_count }}</span>
            </div>
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Vendas</span>
              <span class="font-medium tabular-nums">{{ report.day_totals.sales_count }}</span>
            </div>
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Total vendido</span>
              <span class="font-medium tabular-nums">R$ {{ report.day_totals.sales_total_display }}</span>
            </div>
            <div class="flex flex-col">
              <span class="text-xs text-muted-foreground">Total contado</span>
              <span class="font-medium tabular-nums">R$ {{ report.day_totals.counted_total_display }}</span>
            </div>
          </div>
          <div v-if="report.day_totals.sales_by_method.length" class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">Método</th>
                  <th class="py-1.5 pr-3 font-medium">Pagamentos</th>
                  <th class="py-1.5 font-medium">Valor</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in report.day_totals.sales_by_method"
                  :key="row.method"
                  class="border-b border-border/60 last:border-0"
                >
                  <td class="py-1.5 pr-3 font-medium">{{ row.method_label }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.orders_count }}</td>
                  <td class="py-1.5 tabular-nums">R$ {{ row.amount_display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-xs text-muted-foreground">
            A conferência do contado com o esperado fica na retaguarda.
          </p>
        </section>
      </template>

      <p v-else-if="pending" class="text-sm text-muted-foreground">Carregando relatório…</p>
    </div>
  </main>
</template>
