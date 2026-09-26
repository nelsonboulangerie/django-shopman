<script setup lang="ts">
// ENCOMENDAS · HOJE — "o que sai hoje?". O dia por janela, cada encomenda com a
// situação e o que falta receber. A ordem é a do painel (servidor): janela, e o
// que não combinou horário no fim do dia.
import { isoDate } from "~/presentation/orderTickets";
import {
  PREORDERS_SCOPE_NOTE,
  groupByWindow,
  listSummary,
  todayRange,
} from "~/presentation/preorders";

useHead({ title: "Encomendas de hoje" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const range = ref(todayRange(isoDate(new Date())));
const preorders = usePosPreorders({ key: "pos-preorders-today", range });

const orders = computed(() => preorders.days.value[0]?.orders ?? []);
const groups = computed(() => groupByWindow(orders.value));
const summary = computed(() => listSummary(preorders.count.value, preorders.totalDisplay.value));
</script>

<template>
  <PosPreordersShell :pos="pos" :pending="posPending || preorders.pending.value" @refresh="refreshPos(); preorders.refresh()">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h1 class="text-lg font-semibold">Encomendas de hoje</h1>
      <span v-if="summary" class="text-sm tabular-nums text-muted-foreground" data-preorders-summary>{{ summary }}</span>
    </div>
    <p class="text-sm text-muted-foreground">{{ PREORDERS_SCOPE_NOTE }}</p>

    <p v-if="preorders.pending.value && !preorders.list.value" class="p-4 text-sm text-muted-foreground">
      Carregando as encomendas de hoje…
    </p>

    <p
      v-else-if="preorders.error.value"
      class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
      <span>{{ httpErrorMessage(preorders.error.value, "Não deu para ler as encomendas agora.") }} Tente de novo em Atualizar, no menu ao lado.</span>
    </p>

    <section
      v-else-if="!orders.length"
      class="grid justify-items-center gap-2 rounded-md border border-dashed border-border p-8 text-center"
      data-preorders-empty
    >
      <Icon name="lucide:calendar-check" class="size-6 text-muted-foreground" />
      <p class="text-sm text-muted-foreground">
        Nenhuma encomenda para hoje. As dos próximos dias estão em Semana.
      </p>
      <UiButton variant="outline" size="sm" to="/preorders/week">Ver a semana</UiButton>
    </section>

    <section v-for="group in groups" v-else :key="group.key" class="grid gap-2" data-preorders-window>
      <h2 class="text-sm font-semibold text-muted-foreground">{{ group.label }}</h2>
      <ul class="grid gap-2">
        <li v-for="card in group.orders" :key="card.ref">
          <PosPreorderRow :card="card" />
        </li>
      </ul>
    </section>
  </PosPreordersShell>
</template>
