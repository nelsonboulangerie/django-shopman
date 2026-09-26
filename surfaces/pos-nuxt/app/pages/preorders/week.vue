<script setup lang="ts">
// ENCOMENDAS · SEMANA — "quanto temos para sábado?". A grade: sete colunas (hoje
// e os seis dias seguintes), as encomendas de cada dia por janela, e a conta do
// dia no topo da coluna. Em tela estreita sete colunas não cabem, e a grade vira
// lista por dia — o mesmo conteúdo, na mesma ordem.
//
// A semana começa HOJE e anda de sete em sete: a pergunta é o que vem pela
// frente, e uma semana de segunda a domingo gastaria colunas com o que passou.
//
// O dinheiro: filtro de um toque (Todas · A receber · Pagas), o "A receber" da
// semana no topo e o de cada dia na coluna, ao lado do total do dia. O filtro
// esconde encomendas, nunca muda a conta do dia — a coluna diz o dia inteiro.
import { isoDate } from "~/presentation/orderTickets";
import {
  PREORDERS_SCOPE_NOTE,
  dayColumnTitle,
  dayToReceiveLine,
  filterDaysByPayment,
  filterEmptyMessage,
  flattenDays,
  groupByWindow,
  listSummary,
  parsePaymentFilter,
  paymentCounts,
  preorderCountLabel,
  rangeTitle,
  toReceiveLine,
  weekRange,
} from "~/presentation/preorders";
import type { PaymentFilter } from "~/presentation/preorders";

useHead({ title: "Encomendas da semana" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const today = isoDate(new Date());
const offset = ref(0);
const range = computed(() => weekRange(today, offset.value));
const preorders = usePosPreorders({ key: "pos-preorders-week", range });

const filter = ref<PaymentFilter>(parsePaymentFilter(useRoute().query.pay));

const counts = computed(() => paymentCounts(flattenDays(preorders.days.value)));
const days = computed(() => filterDaysByPayment(preorders.days.value, filter.value));
const shownCount = computed(() => flattenDays(days.value).length);
const summary = computed(() => listSummary(preorders.count.value, preorders.totalDisplay.value));
const toReceive = computed(() => (preorders.list.value
  ? toReceiveLine(preorders.list.value.to_receive_q, preorders.list.value.to_receive_display)
  : ""));
</script>

<template>
  <PosPreordersShell :pos="pos" :pending="posPending || preorders.pending.value" wide @refresh="refreshPos(); preorders.refresh()">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="grid gap-0.5">
        <h1 class="text-lg font-semibold">Encomendas da semana</h1>
        <p class="text-sm text-muted-foreground">
          {{ rangeTitle(range, today) }}<template v-if="summary"> · <span class="tabular-nums" data-preorders-summary>{{ summary }}</span></template>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <UiButton variant="outline" size="sm" data-week-prev @click="offset -= 1">
          <Icon name="lucide:chevron-left" class="size-4" />
          Semana anterior
        </UiButton>
        <UiButton v-if="offset !== 0" variant="ghost" size="sm" data-week-today @click="offset = 0">
          Voltar para hoje
        </UiButton>
        <UiButton variant="outline" size="sm" data-week-next @click="offset += 1">
          Próxima semana
          <Icon name="lucide:chevron-right" class="size-4" />
        </UiButton>
      </div>
    </div>
    <p class="text-sm text-muted-foreground">{{ PREORDERS_SCOPE_NOTE }} Toque numa encomenda para abrir.</p>

    <p v-if="preorders.pending.value && !preorders.list.value" class="p-4 text-sm text-muted-foreground">
      Carregando a semana…
    </p>

    <p
      v-else-if="preorders.error.value"
      class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
      <span>{{ httpErrorMessage(preorders.error.value, "Não deu para ler as encomendas agora.") }} Tente de novo em Atualizar, no menu ao lado.</span>
    </p>

    <template v-else>
      <template v-if="preorders.count.value">
        <p class="text-base font-semibold tabular-nums" data-preorders-to-receive>{{ toReceive }}</p>
        <PosPreorderPaymentFilter v-model="filter" :counts="counts" />
        <p v-if="!shownCount" class="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground" data-preorders-filter-empty>
          {{ filterEmptyMessage(filter) }}
        </p>
      </template>

      <!-- GRADE (tela larga): sete colunas, a conta do dia no topo. -->
      <div class="hidden gap-2 md:grid md:grid-cols-7" data-week-grid>
        <section
          v-for="day in days"
          :key="day.date"
          class="flex min-w-0 flex-col gap-2 rounded-md border bg-muted/30 p-2"
          :class="day.is_today ? 'border-primary/50' : 'border-border'"
          :data-week-day="day.date"
        >
          <header class="grid gap-0.5 border-b border-border pb-2">
            <h2 class="text-sm font-semibold capitalize" :class="day.is_today ? 'text-primary' : ''">{{ dayColumnTitle(day) }}</h2>
            <p class="text-xs tabular-nums text-muted-foreground" data-week-day-total>
              <template v-if="day.orders_count">{{ preorderCountLabel(day.orders_count) }} · {{ day.total_display }}</template>
              <template v-else>Nenhuma encomenda</template>
            </p>
            <p v-if="dayToReceiveLine(day)" class="text-xs font-semibold tabular-nums text-foreground" data-week-day-to-receive>
              {{ dayToReceiveLine(day) }}
            </p>
          </header>
          <template v-for="group in groupByWindow(day.orders)" :key="group.key">
            <p class="text-xs font-medium text-muted-foreground">{{ group.label }}</p>
            <PosPreorderRow v-for="card in group.orders" :key="card.ref" :card="card" compact />
          </template>
        </section>
      </div>

      <!-- LISTA (tela estreita): um bloco por dia, os dias vazios numa linha só. -->
      <div class="grid gap-4 md:hidden" data-week-list>
        <section v-for="day in days" :key="day.date" class="grid gap-2">
          <h2 class="flex flex-wrap items-baseline justify-between gap-2 text-sm font-semibold">
            <span class="capitalize" :class="day.is_today ? 'text-primary' : ''">{{ dayColumnTitle(day) }}</span>
            <span class="text-xs font-normal tabular-nums text-muted-foreground">
              <template v-if="day.orders_count">{{ preorderCountLabel(day.orders_count) }} · {{ day.total_display }}</template>
              <template v-else>Nenhuma encomenda</template>
              <template v-if="dayToReceiveLine(day)"> · <span class="font-semibold text-foreground">{{ dayToReceiveLine(day) }}</span></template>
            </span>
          </h2>
          <template v-for="group in groupByWindow(day.orders)" :key="group.key">
            <p class="text-xs font-medium text-muted-foreground">{{ group.label }}</p>
            <PosPreorderRow v-for="card in group.orders" :key="card.ref" :card="card" />
          </template>
        </section>
      </div>
    </template>
  </PosPreordersShell>
</template>
